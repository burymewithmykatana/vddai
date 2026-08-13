"""Fail-closed loader for one promoted production inference package."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urlparse

import numpy as np
import torch
from pydantic import ValidationError
from torch import Tensor, nn
from torchvision.models import ResNet18_Weights, resnet18

from app.contracts.inference import (
    EXPECTED_PREDICTION_SEMANTICS,
    INFERENCE_CONTRACT_SCHEMA_VERSION,
    MODEL_PACKAGE_SCHEMA_VERSION,
    ONLINE_INPUT_CONTRACT,
    PREPROCESSING_SCHEMA_VERSION,
    InferencePackageLineage,
)
from app.core.config import settings
from ml.anomaly_scorer import (
    AnomalyScoringError,
    NearestNeighborAnomalyScorer,
)
from ml.evaluate_baseline import (
    EVALUATION_CODE_VERSION,
    EVALUATION_SCHEMA_VERSION,
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
from ml.generate_feature_bank import (
    FEATURE_BANK_CODE_VERSION,
    FEATURE_BANK_SCHEMA_VERSION,
    METADATA_FILENAME,
)
from ml.select_threshold import (
    THRESHOLD_ARTIFACT_CODE_VERSION,
    THRESHOLD_ARTIFACT_SCHEMA_VERSION,
    THRESHOLD_FILENAME,
)
from ml.threshold_selector import QUANTILE_METHOD, THRESHOLD_POLICY_NAME

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
    """Base error for production package initialization failures."""


class ModelPackageArtifactError(ModelPackageError):
    """A required artifact is missing, unreadable, or malformed."""


class ModelPackageChecksumError(ModelPackageError):
    """A package member does not match its promoted checksum."""


class ModelPackageCompatibilityError(ModelPackageError):
    """Artifact lineage or runtime dimensions violate the frozen contract."""


class ModelPackageInitializationError(ModelPackageError):
    """Validated artifacts could not initialize a runtime component."""


class FeatureExtractor(Protocol):
    feature_dim: int

    def extract(self, images: Tensor) -> Tensor:
        """Return one feature vector per image."""


ExtractorFactory = Callable[[str], FeatureExtractor]


@dataclass(frozen=True, slots=True)
class ProductionModelPackage:
    """Immutable references to one fully initialized scoring package."""

    feature_extractor: FeatureExtractor
    scorer: NearestNeighborAnomalyScorer
    threshold: float
    lineage: InferencePackageLineage

    def __post_init__(self) -> None:
        if not np.isfinite(self.threshold):
            raise ModelPackageCompatibilityError(
                "Loaded package threshold must be finite."
            )
        if self.threshold != self.lineage.threshold_value:
            raise ModelPackageCompatibilityError(
                "Loaded threshold does not match package lineage."
            )
        if self.feature_extractor.feature_dim != self.lineage.feature_dimension:
            raise ModelPackageCompatibilityError(
                "Loaded extractor dimension does not match package lineage."
            )
        try:
            scorer_dimension = self.scorer.feature_dimension
            scorer_size = self.scorer.bank_size
        except AnomalyScoringError as exc:
            raise ModelPackageInitializationError(
                "Loaded scorer is not ready for inference."
            ) from exc
        if (
            scorer_dimension != self.lineage.feature_dimension
            or scorer_size != self.lineage.feature_bank_sample_count
            or self.scorer.k != self.lineage.scorer_k
        ):
            raise ModelPackageCompatibilityError(
                "Loaded scorer does not match package lineage."
            )

    @property
    def package_id(self) -> str:
        return self.lineage.package_id


def _sha256_file(path: Path, *, artifact_name: str) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as artifact_file:
            for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ModelPackageArtifactError(
            f"{artifact_name} is missing or unreadable."
        ) from exc
    return f"sha256:{digest.hexdigest()}"


def _load_json_object(path: Path, *, artifact_name: str) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ModelPackageArtifactError(
            f"{artifact_name} is missing or unreadable."
        ) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelPackageArtifactError(
            f"{artifact_name} contains malformed JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise ModelPackageArtifactError(f"{artifact_name} must be a JSON object.")
    return payload


def _require_dict(
    payload: dict[str, object],
    key: str,
    *,
    artifact_name: str,
) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ModelPackageCompatibilityError(
            f"{artifact_name} has invalid or missing {key} metadata."
        )
    return value


def _resolve_artifact_member(
    root: Path,
    relative_path: object,
    *,
    artifact_name: str,
) -> Path:
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        raise ModelPackageArtifactError(f"{artifact_name} path is invalid.")
    member = Path(relative_path)
    if member.is_absolute():
        raise ModelPackageArtifactError(
            f"{artifact_name} path must be package-relative."
        )
    resolved_root = root.resolve()
    resolved_member = (resolved_root / member).resolve()
    try:
        resolved_member.relative_to(resolved_root)
    except ValueError as exc:
        raise ModelPackageArtifactError(
            f"{artifact_name} path escapes its configured artifact root."
        ) from exc
    if not resolved_member.is_file():
        raise ModelPackageArtifactError(f"{artifact_name} is missing or unreadable.")
    return resolved_member


def _load_cached_resnet18_extractor(device: str) -> ResNet18FeatureExtractor:
    """Load published weights only from the local torch cache."""
    weights = ResNet18_Weights.DEFAULT
    filename = Path(urlparse(weights.url).path).name
    checkpoint = Path(torch.hub.get_dir()) / "checkpoints" / filename
    if not checkpoint.is_file():
        raise ModelPackageArtifactError(
            "Frozen ResNet-18 weights are missing from the local torch cache."
        )

    expected_hash_prefix = Path(filename).stem.rsplit("-", maxsplit=1)[-1]
    checkpoint_sha256 = _sha256_file(
        checkpoint,
        artifact_name="Frozen ResNet-18 weights",
    ).removeprefix("sha256:")
    if len(expected_hash_prefix) < 8 or not checkpoint_sha256.startswith(
        expected_hash_prefix
    ):
        raise ModelPackageChecksumError(
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
        backbone = nn.Sequential(*list(model.children())[:-1])
        return ResNet18FeatureExtractor(
            config=FeatureExtractorConfig(device=device),
            backbone=backbone,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ModelPackageInitializationError(
            "Frozen ResNet-18 weights are corrupt or incompatible."
        ) from exc


class ModelPackageLoader:
    """Validate all promoted artifacts before returning a ready package."""

    def __init__(
        self,
        *,
        package_manifest_path: Path,
        feature_bank_dir: Path,
        device: str = "cpu",
        extractor_factory: ExtractorFactory | None = None,
    ) -> None:
        self.package_manifest_path = package_manifest_path.resolve()
        self.package_root = self.package_manifest_path.parent
        self.feature_bank_dir = feature_bank_dir.resolve()
        self.device = device
        self.extractor_factory = extractor_factory or (_load_cached_resnet18_extractor)

    def load(self) -> ProductionModelPackage:
        manifest = _load_json_object(
            self.package_manifest_path,
            artifact_name="Package run manifest",
        )
        threshold_path, promoted_threshold_sha256 = self._validate_manifest(manifest)
        threshold_artifact = _load_json_object(
            threshold_path,
            artifact_name="Threshold artifact",
        )
        feature_bank_metadata = _load_json_object(
            self.feature_bank_dir / METADATA_FILENAME,
            artifact_name="Feature-bank metadata",
        )

        (
            features_path,
            features_sha256,
            feature_bank_path,
            sample_count,
        ) = self._validate_feature_bank(feature_bank_metadata)
        (
            threshold,
            scorer_k,
            lineage,
        ) = self._validate_cross_artifact_contract(
            manifest=manifest,
            threshold_artifact=threshold_artifact,
            feature_bank_metadata=feature_bank_metadata,
            promoted_threshold_sha256=promoted_threshold_sha256,
            features_sha256=features_sha256,
            feature_bank_path=feature_bank_path,
            sample_count=sample_count,
        )

        if scorer_k > sample_count:
            raise ModelPackageCompatibilityError(
                "Configured scorer k exceeds the feature-bank size."
            )
        try:
            scorer = NearestNeighborAnomalyScorer(k=scorer_k).load(features_path)
        except AnomalyScoringError as exc:
            raise ModelPackageInitializationError(
                "Feature bank cannot initialize the configured scorer."
            ) from exc

        try:
            extractor = self.extractor_factory(self.device)
        except ModelPackageError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ModelPackageInitializationError(
                "Frozen feature extractor could not be initialized on the configured device."
            ) from exc
        if extractor.feature_dim != RESNET18_FEATURE_DIM:
            raise ModelPackageCompatibilityError(
                "Feature extractor dimension does not match frozen lineage."
            )
        if isinstance(extractor, nn.Module):
            extractor.eval()
            if extractor.training or any(
                parameter.requires_grad for parameter in extractor.parameters()
            ):
                raise ModelPackageCompatibilityError(
                    "Feature extractor must be frozen in evaluation mode."
                )

        return ProductionModelPackage(
            feature_extractor=extractor,
            scorer=scorer,
            threshold=threshold,
            lineage=lineage,
        )

    def _validate_manifest(
        self,
        manifest: dict[str, object],
    ) -> tuple[Path, str]:
        if (
            manifest.get("schema_version") != EVALUATION_SCHEMA_VERSION
            or manifest.get("code_version") != EVALUATION_CODE_VERSION
        ):
            raise ModelPackageCompatibilityError(
                "Unsupported package run-manifest schema or code version."
            )
        if manifest.get("run_type") != "image_level_anomaly_evaluation":
            raise ModelPackageCompatibilityError(
                "Package run manifest has an unsupported run type."
            )
        run_name = manifest.get("run_name")
        if not isinstance(run_name, str) or not run_name:
            raise ModelPackageCompatibilityError(
                "Package run manifest is missing a stable run name."
            )

        protocol = _require_dict(
            manifest,
            "protocol",
            artifact_name="Package run manifest",
        )
        expected_protocol = {
            "feature_bank_fit_split": "train",
            "threshold_selection_split": "validation",
            "evaluation_split": "test",
            "higher_scores_mean": "more_anomalous",
            "prediction_rule": "score > threshold",
            "retune_after_test_evaluation": False,
        }
        if any(protocol.get(key) != value for key, value in expected_protocol.items()):
            raise ModelPackageCompatibilityError(
                "Package run protocol violates frozen inference semantics."
            )

        artifacts = _require_dict(
            manifest,
            "artifacts",
            artifact_name="Package run manifest",
        )
        threshold_file = _require_dict(
            artifacts,
            THRESHOLD_FILENAME,
            artifact_name="Package run manifest",
        )
        threshold_path = _resolve_artifact_member(
            self.package_root,
            threshold_file.get("path"),
            artifact_name="Promoted threshold artifact",
        )
        expected_sha256 = threshold_file.get("sha256")
        actual_sha256 = _sha256_file(
            threshold_path,
            artifact_name="Promoted threshold artifact",
        )
        if not isinstance(expected_sha256, str) or actual_sha256 != expected_sha256:
            raise ModelPackageChecksumError(
                "Promoted threshold artifact checksum does not match the run manifest."
            )
        return threshold_path, actual_sha256

    def _validate_feature_bank(
        self,
        metadata: dict[str, object],
    ) -> tuple[Path, str, str, int]:
        if (
            metadata.get("schema_version") != FEATURE_BANK_SCHEMA_VERSION
            or metadata.get("code_version") != FEATURE_BANK_CODE_VERSION
        ):
            raise ModelPackageCompatibilityError(
                "Unsupported feature-bank schema or code version."
            )
        if metadata.get("split") != "train":
            raise ModelPackageCompatibilityError(
                "Production feature bank must contain training records only."
            )
        if metadata.get("feature_extractor") != EXPECTED_EXTRACTOR:
            raise ModelPackageCompatibilityError(
                "Feature-bank extractor lineage is incompatible."
            )
        _, expected_height, expected_width = ONLINE_INPUT_CONTRACT.storage_tensor_shape
        if metadata.get("image_size") != {
            "height": expected_height,
            "width": expected_width,
        }:
            raise ModelPackageCompatibilityError(
                "Feature-bank image size does not match preprocessing contract."
            )

        sample_count = metadata.get("sample_count")
        dataset_version = metadata.get("dataset_version")
        manifest_fingerprint = metadata.get("manifest_fingerprint")
        if (
            not isinstance(sample_count, int)
            or isinstance(sample_count, bool)
            or sample_count <= 0
            or not isinstance(dataset_version, str)
            or not dataset_version
            or not isinstance(manifest_fingerprint, str)
            or len(manifest_fingerprint) != 71
            or not manifest_fingerprint.startswith("sha256:")
        ):
            raise ModelPackageCompatibilityError("Feature-bank lineage is incomplete.")

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
            self.feature_bank_dir,
            feature_file.get("path"),
            artifact_name="Feature-bank archive",
        )
        expected_checksum = feature_file.get("sha256")
        actual_checksum = _sha256_file(
            features_path,
            artifact_name="Feature-bank archive",
        )
        if (
            not isinstance(expected_checksum, str)
            or actual_checksum != expected_checksum
        ):
            raise ModelPackageChecksumError(
                "Feature-bank archive checksum does not match metadata."
            )

        self._validate_feature_archive(
            features_path=features_path,
            sample_count=sample_count,
            dataset_version=dataset_version,
        )
        return (
            features_path,
            actual_checksum,
            str(feature_file["path"]),
            sample_count,
        )

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
                    raise ModelPackageCompatibilityError(
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
            raise ModelPackageArtifactError(
                "Feature-bank archive is corrupt or incompatible."
            ) from exc

        if (
            features.shape != (sample_count, RESNET18_FEATURE_DIM)
            or features.dtype != np.float32
            or not np.isfinite(features).all()
        ):
            raise ModelPackageCompatibilityError(
                "Feature-bank feature matrix violates the frozen dimension or dtype."
            )
        for values in (sample_ids, source_paths, splits, dataset_versions):
            if values.ndim != 1 or values.shape[0] != sample_count:
                raise ModelPackageCompatibilityError(
                    "Feature-bank lineage arrays do not align with features."
                )
        if len(set(sample_ids.tolist())) != sample_count:
            raise ModelPackageCompatibilityError(
                "Feature-bank sample IDs must be unique."
            )
        if set(splits.tolist()) != {"train"}:
            raise ModelPackageCompatibilityError(
                "Feature-bank archive must contain training records only."
            )
        if set(dataset_versions.tolist()) != {dataset_version}:
            raise ModelPackageCompatibilityError(
                "Feature-bank dataset versions do not match metadata."
            )

    def _validate_cross_artifact_contract(
        self,
        *,
        manifest: dict[str, object],
        threshold_artifact: dict[str, object],
        feature_bank_metadata: dict[str, object],
        promoted_threshold_sha256: str,
        features_sha256: str,
        feature_bank_path: str,
        sample_count: int,
    ) -> tuple[float, int, InferencePackageLineage]:
        if (
            threshold_artifact.get("schema_version")
            != THRESHOLD_ARTIFACT_SCHEMA_VERSION
            or threshold_artifact.get("code_version") != THRESHOLD_ARTIFACT_CODE_VERSION
        ):
            raise ModelPackageCompatibilityError(
                "Unsupported threshold schema or code version."
            )
        if threshold_artifact.get("feature_extractor") != EXPECTED_EXTRACTOR:
            raise ModelPackageCompatibilityError(
                "Threshold extractor lineage is incompatible."
            )
        if threshold_artifact.get("prediction_semantics") != (
            EXPECTED_PREDICTION_SEMANTICS
        ):
            raise ModelPackageCompatibilityError(
                "Threshold prediction semantics are incompatible."
            )

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
            or calibration.get("quantile_method") != QUANTILE_METHOD
        ):
            raise ModelPackageCompatibilityError(
                "Threshold must be frozen from normal validation data only."
            )

        threshold_selection = _require_dict(
            threshold_artifact,
            "threshold_selection",
            artifact_name="Threshold artifact",
        )
        threshold_value = threshold_selection.get("threshold")
        quantile_value = threshold_selection.get("quantile")
        if isinstance(threshold_value, bool) or isinstance(quantile_value, bool):
            raise ModelPackageCompatibilityError(
                "Threshold selection values must be numeric and finite."
            )
        try:
            threshold = float(threshold_value)
            quantile = float(quantile_value)
        except (TypeError, ValueError) as exc:
            raise ModelPackageCompatibilityError(
                "Threshold selection values must be numeric and finite."
            ) from exc
        if (
            threshold_selection.get("threshold_policy") != THRESHOLD_POLICY_NAME
            or not np.isfinite(threshold)
            or not np.isfinite(quantile)
            or not 0.0 <= quantile <= 1.0
        ):
            raise ModelPackageCompatibilityError(
                "Threshold selection metadata is incompatible."
            )

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
            raise ModelPackageCompatibilityError("Scorer lineage is incompatible.")

        expected_feature_bank_lineage = {
            "schema_version": feature_bank_metadata["schema_version"],
            "code_version": feature_bank_metadata["code_version"],
            "dataset_version": feature_bank_metadata["dataset_version"],
            "sample_count": sample_count,
            "split": feature_bank_metadata["split"],
            "features_sha256": features_sha256,
        }
        threshold_feature_bank = _require_dict(
            threshold_artifact,
            "feature_bank",
            artifact_name="Threshold artifact",
        )
        dataset = _require_dict(
            threshold_artifact,
            "dataset",
            artifact_name="Threshold artifact",
        )
        if threshold_feature_bank != expected_feature_bank_lineage:
            raise ModelPackageCompatibilityError(
                "Threshold and feature-bank lineage do not match."
            )
        if (
            dataset.get("name") != "MVTec AD"
            or dataset.get("category") != "tile"
            or dataset.get("version") != feature_bank_metadata["dataset_version"]
            or dataset.get("manifest_fingerprint")
            != feature_bank_metadata["manifest_fingerprint"]
        ):
            raise ModelPackageCompatibilityError("Dataset lineage is incompatible.")

        manifest_lineage = _require_dict(
            manifest,
            "lineage",
            artifact_name="Package run manifest",
        )
        manifest_effective_configuration = _require_dict(
            manifest,
            "effective_configuration",
            artifact_name="Package run manifest",
        )
        manifest_threshold_policy = _require_dict(
            manifest,
            "threshold_policy",
            artifact_name="Package run manifest",
        )
        if (
            manifest_lineage.get("dataset") != dataset
            or manifest_lineage.get("feature_bank") != threshold_feature_bank
            or manifest_lineage.get("feature_extractor") != EXPECTED_EXTRACTOR
            or manifest_effective_configuration.get("scorer") != scorer
            or manifest_effective_configuration.get("threshold_quantile") != quantile
            or manifest_threshold_policy
            != {
                "name": THRESHOLD_POLICY_NAME,
                "quantile": quantile,
                "threshold": threshold,
                "calibration_split": "validation",
                "calibration_mode": "normal_only",
            }
        ):
            raise ModelPackageCompatibilityError(
                "Run manifest and serving artifacts have incompatible lineage."
            )

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
                "name": THRESHOLD_POLICY_NAME,
                "quantile": quantile,
                "value": threshold,
            },
            "threshold_artifact_sha256": promoted_threshold_sha256,
        }
        canonical_identity = json.dumps(
            package_identity,
            sort_keys=True,
            separators=(",", ":"),
        )
        package_digest = hashlib.sha256(canonical_identity.encode("utf-8")).hexdigest()
        package_id = f"mvtec-tile-resnet18-knn-{package_digest[:16]}"

        try:
            lineage = InferencePackageLineage(
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
                feature_bank_sha256=features_sha256,
                feature_bank_sample_count=sample_count,
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
                threshold_artifact_sha256=promoted_threshold_sha256,
            )
        except ValidationError as exc:
            raise ModelPackageCompatibilityError(
                "Validated artifact lineage cannot satisfy the inference contract."
            ) from exc
        return threshold, scorer_k, lineage


@lru_cache(maxsize=2)
def load_promoted_model_package(
    selection: "PromotedModelSelection",
) -> ProductionModelPackage:
    """Load and cache a package by its immutable promoted selection."""
    package = ModelPackageLoader(
        package_manifest_path=selection.package_manifest_path,
        feature_bank_dir=selection.feature_bank_dir,
        device=settings.MODEL_DEVICE,
    ).load()
    from app.services.promoted_model_resolver import validate_selected_package

    validate_selected_package(selection, package)
    return package


def resolve_production_model_selection() -> "PromotedModelSelection":
    """Read the current production pointer without scanning artifact folders."""
    from app.services.promoted_model_resolver import PromotedModelResolver

    return PromotedModelResolver(
        Path(settings.MODEL_REGISTRY_PATH),
        repository_root=Path(settings.MODEL_ARTIFACT_ROOT),
    ).resolve()


def get_production_model_package() -> ProductionModelPackage:
    """Resolve the active version and reuse its already-loaded package."""
    return load_promoted_model_package(resolve_production_model_selection())


def reset_model_package_cache_for_tests() -> None:
    """Clear process package state only in the test environment."""
    if settings.ENVIRONMENT != "test":
        raise RuntimeError("Model-package cache reset is restricted to tests.")
    load_promoted_model_package.cache_clear()


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.promoted_model_resolver import PromotedModelSelection
