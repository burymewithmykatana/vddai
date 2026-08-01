"""Frozen Week 5 image-level anomaly inference package."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import numpy as np
import torch
from torch import Tensor, nn
from torchvision.models import ResNet18_Weights, resnet18

from app.contracts.inference import (
    EXPECTED_PREDICTION_SEMANTICS,
    INFERENCE_CONTRACT_SCHEMA_VERSION,
    MODEL_PACKAGE_SCHEMA_VERSION,
    ONLINE_INPUT_CONTRACT,
    PREPROCESSING_SCHEMA_VERSION,
    AnomalyInferenceResult,
    InferencePackageLineage,
    classify_anomaly_score,
)
from app.core.config import settings
from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
    image_preprocessing_service,
)
from ml.anomaly_scorer import (
    AnomalyScoringError,
    NearestNeighborAnomalyScorer,
)
from ml.feature_extractor import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    RESNET18_EXTRACTOR_NAME,
    RESNET18_FEATURE_DIM,
    RESNET18_FEATURE_LAYER,
    RESNET18_WEIGHTS_IDENTIFIER,
    FeatureExtractorConfig,
    ResNet18FeatureExtractor,
)
from ml.generate_feature_bank import FEATURE_BANK_SCHEMA_VERSION
from ml.select_threshold import THRESHOLD_ARTIFACT_SCHEMA_VERSION
from ml.threshold_selector import THRESHOLD_POLICY_NAME

logger = logging.getLogger(__name__)

EXPECTED_EXTRACTOR = {
    "name": RESNET18_EXTRACTOR_NAME,
    "pretrained_weights": RESNET18_WEIGHTS_IDENTIFIER,
    "feature_layer": RESNET18_FEATURE_LAYER,
    "feature_dimension": RESNET18_FEATURE_DIM,
    "normalization": {
        "operation": "channelwise_standardization",
        "mean": list(IMAGENET_MEAN),
        "std": list(IMAGENET_STD),
    },
}


class ModelPackageError(RuntimeError):
    """Raised when frozen production artifacts cannot be trusted or loaded."""


class FeatureExtractor(Protocol):
    feature_dim: int

    def extract(self, images: Tensor) -> Tensor:
        """Return one feature vector per image."""


ModelPackageMetadata = InferencePackageLineage


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as artifact_file:
            for chunk in iter(
                lambda: artifact_file.read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)
    except OSError as exc:
        raise ModelPackageError(
            f"Artifact could not be read: {path.as_posix()}"
        ) from exc
    return f"sha256:{digest.hexdigest()}"


def _load_json_object(path: Path, *, artifact_name: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelPackageError(f"{artifact_name} could not be loaded.") from exc

    if not isinstance(payload, dict):
        raise ModelPackageError(f"{artifact_name} must be a JSON object.")
    return payload


def _require_dict(
    payload: dict[str, object],
    key: str,
    *,
    artifact_name: str,
) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ModelPackageError(
            f"{artifact_name} has invalid or missing {key} metadata."
        )
    return value


def _resolve_artifact_member(root: Path, relative_path: object) -> Path:
    if not isinstance(relative_path, str):
        raise ModelPackageError("Feature-bank archive path is invalid.")

    member = Path(relative_path)
    if member.is_absolute():
        raise ModelPackageError("Feature-bank archive path must be relative.")

    resolved_root = root.resolve()
    resolved_member = (resolved_root / member).resolve()
    try:
        resolved_member.relative_to(resolved_root)
    except ValueError as exc:
        raise ModelPackageError(
            "Feature-bank archive path escapes its artifact directory."
        ) from exc
    return resolved_member


def _load_cached_resnet18_extractor(device: str) -> ResNet18FeatureExtractor:
    weights = ResNet18_Weights.DEFAULT
    filename = Path(urlparse(weights.url).path).name
    checkpoint = Path(torch.hub.get_dir()) / "checkpoints" / filename

    if not checkpoint.is_file():
        raise ModelPackageError(
            "Frozen ResNet-18 weights are not present in the local torch "
            f"cache: {checkpoint.as_posix()}"
        )

    expected_hash_prefix = Path(filename).stem.rsplit("-", maxsplit=1)[-1]
    checkpoint_sha256 = _sha256_file(checkpoint).removeprefix("sha256:")
    if len(expected_hash_prefix) < 8 or not checkpoint_sha256.startswith(
        expected_hash_prefix
    ):
        raise ModelPackageError(
            "Frozen ResNet-18 weights failed their published checksum."
        )

    try:
        state_dict = torch.load(
            checkpoint,
            map_location="cpu",
            weights_only=True,
        )
        model = resnet18(weights=None)
        model.load_state_dict(state_dict, strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ModelPackageError(
            "Frozen ResNet-18 weights are corrupt or incompatible."
        ) from exc

    backbone = nn.Sequential(*list(model.children())[:-1])
    return ResNet18FeatureExtractor(
        config=FeatureExtractorConfig(device=device),
        backbone=backbone,
    )


class AnomalyInferenceService:
    """Load one immutable artifact package and serve deterministic inference."""

    def __init__(
        self,
        *,
        feature_bank_dir: Path,
        threshold_artifact_path: Path,
        preprocessing_service: ImagePreprocessingService = (
            image_preprocessing_service
        ),
        feature_extractor: FeatureExtractor | None = None,
        device: str = "cpu",
    ) -> None:
        self.preprocessing_service = preprocessing_service
        _, contract_height, contract_width = ONLINE_INPUT_CONTRACT.storage_tensor_shape
        if (
            self.preprocessing_service.target_width != contract_width
            or self.preprocessing_service.target_height != contract_height
        ):
            raise ModelPackageError(
                "Preprocessing dimensions do not match the production contract."
            )
        self._feature_bank_dir = feature_bank_dir.resolve()
        self._threshold_artifact_path = threshold_artifact_path.resolve()

        feature_bank_metadata = _load_json_object(
            self._feature_bank_dir / "metadata.json",
            artifact_name="Feature-bank metadata",
        )
        threshold_artifact = _load_json_object(
            self._threshold_artifact_path,
            artifact_name="Threshold artifact",
        )

        (
            features_path,
            expected_features_sha256,
            feature_bank_path,
        ) = self._validate_feature_bank(feature_bank_metadata)
        threshold, scorer_k, package_metadata = self._validate_threshold(
            threshold_artifact=threshold_artifact,
            feature_bank_metadata=feature_bank_metadata,
            expected_features_sha256=expected_features_sha256,
            feature_bank_path=feature_bank_path,
        )

        try:
            scorer = NearestNeighborAnomalyScorer(k=scorer_k).load(features_path)
        except AnomalyScoringError as exc:
            raise ModelPackageError(
                "Feature bank cannot initialize the anomaly scorer."
            ) from exc

        if (
            scorer.feature_dimension != RESNET18_FEATURE_DIM
            or scorer.bank_size != package_metadata.feature_bank_sample_count
        ):
            raise ModelPackageError(
                "Feature-bank array shape does not match frozen lineage."
            )

        extractor = feature_extractor or _load_cached_resnet18_extractor(device)
        if extractor.feature_dim != RESNET18_FEATURE_DIM:
            raise ModelPackageError(
                "Feature extractor dimension does not match frozen lineage."
            )

        self.threshold = threshold
        self.scorer = scorer
        self.feature_extractor = extractor
        self.package_metadata = package_metadata

    def _validate_feature_bank(
        self,
        metadata: dict[str, object],
    ) -> tuple[Path, str, str]:
        if metadata.get("schema_version") != FEATURE_BANK_SCHEMA_VERSION:
            raise ModelPackageError("Unsupported feature-bank schema version.")
        if metadata.get("split") != "train":
            raise ModelPackageError(
                "Production feature bank must contain training records only."
            )
        if metadata.get("feature_extractor") != EXPECTED_EXTRACTOR:
            raise ModelPackageError("Feature-bank extractor lineage is incompatible.")
        if metadata.get("image_size") != {
            "height": self.preprocessing_service.target_height,
            "width": self.preprocessing_service.target_width,
        }:
            raise ModelPackageError(
                "Feature-bank image size does not match preprocessing."
            )

        sample_count = metadata.get("sample_count")
        dataset_version = metadata.get("dataset_version")
        code_version = metadata.get("code_version")
        manifest_fingerprint = metadata.get("manifest_fingerprint")
        if (
            not isinstance(sample_count, int)
            or isinstance(sample_count, bool)
            or sample_count <= 0
            or not isinstance(dataset_version, str)
            or not dataset_version
            or not isinstance(code_version, str)
            or not code_version
            or not isinstance(manifest_fingerprint, str)
            or not manifest_fingerprint.startswith("sha256:")
        ):
            raise ModelPackageError("Feature-bank lineage is incomplete.")

        files = _require_dict(
            metadata,
            "files",
            artifact_name="Feature-bank metadata",
        )
        feature_file = _require_dict(
            files,
            "features",
            artifact_name="Feature-bank metadata",
        )
        features_path = _resolve_artifact_member(
            self._feature_bank_dir,
            feature_file.get("path"),
        )
        expected_checksum = feature_file.get("sha256")
        if (
            not isinstance(expected_checksum, str)
            or _sha256_file(features_path) != expected_checksum
        ):
            raise ModelPackageError(
                "Feature-bank archive checksum does not match metadata."
            )

        self._validate_feature_archive(
            features_path=features_path,
            sample_count=sample_count,
            dataset_version=dataset_version,
        )
        return features_path, expected_checksum, str(feature_file["path"])

    @staticmethod
    def _validate_feature_archive(
        *,
        features_path: Path,
        sample_count: int,
        dataset_version: str,
    ) -> None:
        required_arrays = {
            "features",
            "sample_ids",
            "source_paths",
            "splits",
            "dataset_versions",
        }
        try:
            with np.load(features_path, allow_pickle=False) as archive:
                if not required_arrays.issubset(archive.files):
                    raise ModelPackageError(
                        "Feature-bank archive lineage arrays are incomplete."
                    )
                features = archive["features"]
                sample_ids = archive["sample_ids"]
                source_paths = archive["source_paths"]
                splits = archive["splits"]
                dataset_versions = archive["dataset_versions"]
        except ModelPackageError:
            raise
        except (OSError, ValueError, KeyError) as exc:
            raise ModelPackageError(
                "Feature-bank archive is corrupt or incompatible."
            ) from exc

        expected_shape = (sample_count, RESNET18_FEATURE_DIM)
        if features.shape != expected_shape:
            raise ModelPackageError("Feature-bank array shape does not match metadata.")
        for values in (sample_ids, source_paths, splits, dataset_versions):
            if values.ndim != 1 or values.shape[0] != sample_count:
                raise ModelPackageError(
                    "Feature-bank lineage arrays do not align with features."
                )
        if len(set(sample_ids.tolist())) != sample_count:
            raise ModelPackageError("Feature-bank sample IDs must be unique.")
        if set(splits.tolist()) != {"train"}:
            raise ModelPackageError(
                "Feature-bank archive must contain training records only."
            )
        if set(dataset_versions.tolist()) != {dataset_version}:
            raise ModelPackageError(
                "Feature-bank dataset versions do not match metadata."
            )

    def _validate_threshold(
        self,
        *,
        threshold_artifact: dict[str, object],
        feature_bank_metadata: dict[str, object],
        expected_features_sha256: str,
        feature_bank_path: str,
    ) -> tuple[float, int, ModelPackageMetadata]:
        if threshold_artifact.get("schema_version") != (
            THRESHOLD_ARTIFACT_SCHEMA_VERSION
        ):
            raise ModelPackageError("Unsupported threshold schema version.")
        if threshold_artifact.get("feature_extractor") != EXPECTED_EXTRACTOR:
            raise ModelPackageError("Threshold extractor lineage is incompatible.")
        if threshold_artifact.get("prediction_semantics") != (
            EXPECTED_PREDICTION_SEMANTICS
        ):
            raise ModelPackageError("Threshold prediction semantics are incompatible.")

        calibration = _require_dict(
            threshold_artifact,
            "calibration",
            artifact_name="Threshold artifact",
        )
        if (
            calibration.get("split") != "validation"
            or calibration.get("mode") != "normal_only"
            or calibration.get("uses_test_scores") is not False
            or calibration.get("uses_test_labels") is not False
        ):
            raise ModelPackageError(
                "Threshold must be frozen from normal validation data only."
            )

        threshold_selection = _require_dict(
            threshold_artifact,
            "threshold_selection",
            artifact_name="Threshold artifact",
        )
        threshold_policy = threshold_selection.get("threshold_policy")
        threshold_value = threshold_selection.get("threshold")
        quantile_value = threshold_selection.get("quantile")
        try:
            threshold = float(threshold_value)
            quantile = float(quantile_value)
        except (TypeError, ValueError) as exc:
            raise ModelPackageError(
                "Threshold selection values must be numeric."
            ) from exc
        if (
            threshold_policy != THRESHOLD_POLICY_NAME
            or not np.isfinite(threshold)
            or not np.isfinite(quantile)
            or not 0.0 <= quantile <= 1.0
        ):
            raise ModelPackageError("Threshold selection metadata is incompatible.")

        scorer = _require_dict(
            threshold_artifact,
            "scorer",
            artifact_name="Threshold artifact",
        )
        scorer_k = scorer.get("k")
        if (
            scorer.get("distance") != "euclidean"
            or scorer.get("aggregation") != "mean_k_nearest"
            or scorer.get("higher_is_more_anomalous") is not True
            or not isinstance(scorer_k, int)
            or isinstance(scorer_k, bool)
            or scorer_k <= 0
        ):
            raise ModelPackageError("Scorer lineage is incompatible.")

        threshold_feature_bank = _require_dict(
            threshold_artifact,
            "feature_bank",
            artifact_name="Threshold artifact",
        )
        expected_feature_bank_lineage = {
            "schema_version": feature_bank_metadata["schema_version"],
            "code_version": feature_bank_metadata["code_version"],
            "dataset_version": feature_bank_metadata["dataset_version"],
            "sample_count": feature_bank_metadata["sample_count"],
            "split": feature_bank_metadata["split"],
            "features_sha256": expected_features_sha256,
        }
        if threshold_feature_bank != expected_feature_bank_lineage:
            raise ModelPackageError("Threshold and feature-bank lineage do not match.")

        dataset = _require_dict(
            threshold_artifact,
            "dataset",
            artifact_name="Threshold artifact",
        )
        if (
            dataset.get("name") != "MVTec AD"
            or dataset.get("category") != "tile"
            or dataset.get("version") != feature_bank_metadata["dataset_version"]
            or dataset.get("manifest_fingerprint")
            != feature_bank_metadata["manifest_fingerprint"]
        ):
            raise ModelPackageError("Dataset lineage is incompatible.")

        package_identity = {
            "contract_schema_version": INFERENCE_CONTRACT_SCHEMA_VERSION,
            "schema_version": MODEL_PACKAGE_SCHEMA_VERSION,
            "preprocessing_schema_version": PREPROCESSING_SCHEMA_VERSION,
            "dataset": dataset,
            "feature_bank": threshold_feature_bank,
            "feature_bank_path": feature_bank_path,
            "feature_extractor": EXPECTED_EXTRACTOR,
            "scorer": scorer,
            "threshold_policy": {
                "name": threshold_policy,
                "quantile": quantile,
                "value": threshold,
            },
            "threshold_artifact_sha256": _sha256_file(self._threshold_artifact_path),
        }
        canonical_identity = json.dumps(
            package_identity,
            sort_keys=True,
            separators=(",", ":"),
        )
        package_digest = hashlib.sha256(canonical_identity.encode("utf-8")).hexdigest()
        package_id = f"mvtec-tile-resnet18-knn-{package_digest[:16]}"

        return (
            threshold,
            scorer_k,
            ModelPackageMetadata(
                contract_schema_version=INFERENCE_CONTRACT_SCHEMA_VERSION,
                schema_version=MODEL_PACKAGE_SCHEMA_VERSION,
                package_id=package_id,
                preprocessing_schema_version=PREPROCESSING_SCHEMA_VERSION,
                dataset_name=str(dataset["name"]),
                dataset_category=str(dataset["category"]),
                dataset_version=str(dataset["version"]),
                manifest_fingerprint=str(dataset["manifest_fingerprint"]),
                feature_bank_schema_version=str(
                    threshold_feature_bank["schema_version"]
                ),
                feature_bank_code_version=str(threshold_feature_bank["code_version"]),
                feature_bank_path=feature_bank_path,
                feature_bank_sha256=expected_features_sha256,
                feature_bank_sample_count=int(threshold_feature_bank["sample_count"]),
                extractor_name=RESNET18_EXTRACTOR_NAME,
                extractor_weights=RESNET18_WEIGHTS_IDENTIFIER,
                extractor_layer=RESNET18_FEATURE_LAYER,
                feature_dimension=RESNET18_FEATURE_DIM,
                scorer_distance="euclidean",
                scorer_aggregation="mean_k_nearest",
                scorer_k=scorer_k,
                threshold_policy=THRESHOLD_POLICY_NAME,
                threshold_quantile=quantile,
                threshold_value=threshold,
                threshold_artifact_sha256=str(
                    package_identity["threshold_artifact_sha256"]
                ),
            ),
        )

    def predict(self, image_path: str | Path) -> AnomalyInferenceResult:
        started_at = time.perf_counter()
        preprocessed = self.preprocessing_service.preprocess(image_path)
        images = torch.from_numpy(preprocessed.array).unsqueeze(0)

        features = self.feature_extractor.extract(images)
        scores = self.scorer.score(features.detach().to("cpu").numpy())
        if scores.shape != (1,):
            raise ModelPackageError("Inference must produce exactly one anomaly score.")

        score = float(scores[0])
        predicted_label = classify_anomaly_score(
            score=score,
            threshold=self.threshold,
        )
        latency_ms = max(0, round((time.perf_counter() - started_at) * 1000))

        logger.info(
            "anomaly_inference_completed package_id=%s label=%s score=%s "
            "threshold=%s latency_ms=%s",
            self.package_metadata.package_id,
            predicted_label,
            score,
            self.threshold,
            latency_ms,
        )
        return AnomalyInferenceResult(
            predicted_label=predicted_label,
            anomaly_score=score,
            threshold=self.threshold,
            model_version=self.package_metadata.package_id,
            model_lineage=self.package_metadata,
            latency_ms=latency_ms,
        )


@lru_cache(maxsize=1)
def get_anomaly_inference_service() -> AnomalyInferenceService:
    """Load production artifacts lazily once per worker process."""
    return AnomalyInferenceService(
        feature_bank_dir=Path(settings.FEATURE_BANK_DIR),
        threshold_artifact_path=Path(settings.THRESHOLD_ARTIFACT_PATH),
        device=settings.MODEL_DEVICE,
    )
