import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image
from torch import Tensor

from app.services.anomaly_inference_service import (
    EXPECTED_EXTRACTOR,
    MODEL_PACKAGE_SCHEMA_VERSION,
    AnomalyInferenceService,
    ModelPackageError,
)
from app.services.image_preprocessing_service import ImagePreprocessingService
from ml.generate_feature_bank import (
    FEATURE_BANK_CODE_VERSION,
    FEATURE_BANK_SCHEMA_VERSION,
)
from ml.select_threshold import (
    THRESHOLD_ARTIFACT_CODE_VERSION,
    THRESHOLD_ARTIFACT_SCHEMA_VERSION,
)
from ml.threshold_selector import THRESHOLD_POLICY_NAME


class ConstantFeatureExtractor:
    feature_dim = 512

    def __init__(self, value: float) -> None:
        self.value = value
        self.received_images: Tensor | None = None

    def extract(self, images: Tensor) -> Tensor:
        self.received_images = images.clone()
        features = torch.zeros((images.shape[0], self.feature_dim))
        features[:, 0] = self.value
        return features


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def write_package(
    root: Path,
    *,
    threshold: float = 2.0,
) -> tuple[Path, Path]:
    feature_bank_dir = root / "feature-bank"
    feature_bank_dir.mkdir(parents=True)
    features_path = feature_bank_dir / "features.npz"
    np.savez_compressed(
        features_path,
        features=np.zeros((2, 512), dtype=np.float32),
        sample_ids=np.asarray(["normal-1", "normal-2"], dtype=np.str_),
        source_paths=np.asarray(["a.png", "b.png"], dtype=np.str_),
        splits=np.asarray(["train", "train"], dtype=np.str_),
        dataset_versions=np.asarray(["dataset-v1", "dataset-v1"]),
    )
    feature_checksum = sha256_file(features_path)
    feature_bank_metadata = {
        "schema_version": FEATURE_BANK_SCHEMA_VERSION,
        "code_version": FEATURE_BANK_CODE_VERSION,
        "created_at": "2026-08-01T00:00:00Z",
        "split": "train",
        "sample_count": 2,
        "dataset_version": "dataset-v1",
        "manifest_fingerprint": f"sha256:{'a' * 64}",
        "random_seed": 42,
        "image_size": {"height": 224, "width": 224},
        "feature_extractor": EXPECTED_EXTRACTOR,
        "files": {
            "features": {
                "path": "features.npz",
                "sha256": feature_checksum,
            }
        },
    }
    (feature_bank_dir / "metadata.json").write_text(
        json.dumps(feature_bank_metadata),
        encoding="utf-8",
    )

    threshold_path = root / "threshold.json"
    threshold_artifact = {
        "schema_version": THRESHOLD_ARTIFACT_SCHEMA_VERSION,
        "code_version": THRESHOLD_ARTIFACT_CODE_VERSION,
        "created_at": "2026-08-01T00:00:00Z",
        "calibration": {
            "split": "validation",
            "mode": "normal_only",
            "uses_test_scores": False,
            "uses_test_labels": False,
            "quantile_method": "linear",
        },
        "prediction_semantics": {
            "anomalous": "score > threshold",
            "normal": "score <= threshold",
        },
        "threshold_selection": {
            "threshold": threshold,
            "quantile": 0.95,
            "threshold_policy": THRESHOLD_POLICY_NAME,
        },
        "dataset": {
            "name": "MVTec AD",
            "category": "tile",
            "version": "dataset-v1",
            "manifest_fingerprint": f"sha256:{'a' * 64}",
        },
        "feature_bank": {
            "schema_version": FEATURE_BANK_SCHEMA_VERSION,
            "code_version": FEATURE_BANK_CODE_VERSION,
            "dataset_version": "dataset-v1",
            "sample_count": 2,
            "split": "train",
            "features_sha256": feature_checksum,
        },
        "feature_extractor": EXPECTED_EXTRACTOR,
        "scorer": {
            "distance": "euclidean",
            "aggregation": "mean_k_nearest",
            "k": 1,
            "higher_is_more_anomalous": True,
        },
    }
    threshold_path.write_text(json.dumps(threshold_artifact), encoding="utf-8")
    return feature_bank_dir, threshold_path


def write_image(path: Path) -> None:
    Image.new("RGB", (16, 16), color=(120, 80, 40)).save(path)


def test_inference_uses_exact_score_strict_threshold_and_lineage(
    tmp_path: Path,
) -> None:
    feature_bank_dir, threshold_path = write_package(tmp_path, threshold=2.0)
    image_path = tmp_path / "image.png"
    write_image(image_path)
    extractor = ConstantFeatureExtractor(value=2.0)
    service = AnomalyInferenceService(
        feature_bank_dir=feature_bank_dir,
        threshold_artifact_path=threshold_path,
        feature_extractor=extractor,
    )

    equal_result = service.predict(image_path)

    assert equal_result.anomaly_score == pytest.approx(2.0)
    assert equal_result.predicted_label.value == "normal"
    assert equal_result.threshold == pytest.approx(2.0)
    assert equal_result.model_version.startswith("mvtec-tile-resnet18-knn-")
    assert equal_result.model_lineage.schema_version == (MODEL_PACKAGE_SCHEMA_VERSION)
    assert equal_result.model_lineage.dataset_category == "tile"
    assert equal_result.model_lineage.scorer_k == 1
    assert equal_result.model_lineage.preprocessing_schema_version == (
        "vddai.preprocessing.rgb_chw_bilinear.v1"
    )
    assert extractor.received_images is not None
    assert extractor.received_images.shape == (1, 3, 224, 224)
    assert extractor.received_images.dtype == torch.float32
    assert extractor.received_images.min().item() >= 0.0
    assert extractor.received_images.max().item() <= 1.0


def test_score_above_threshold_is_anomalous(tmp_path: Path) -> None:
    feature_bank_dir, threshold_path = write_package(tmp_path, threshold=1.9)
    image_path = tmp_path / "image.png"
    write_image(image_path)
    service = AnomalyInferenceService(
        feature_bank_dir=feature_bank_dir,
        threshold_artifact_path=threshold_path,
        feature_extractor=ConstantFeatureExtractor(value=2.0),
    )

    result = service.predict(image_path)

    assert result.predicted_label.value == "anomalous"


def test_corrupt_feature_bank_fails_closed(tmp_path: Path) -> None:
    feature_bank_dir, threshold_path = write_package(tmp_path)
    with (feature_bank_dir / "features.npz").open("ab") as feature_file:
        feature_file.write(b"corruption")

    with pytest.raises(
        ModelPackageError,
        match="checksum does not match",
    ):
        AnomalyInferenceService(
            feature_bank_dir=feature_bank_dir,
            threshold_artifact_path=threshold_path,
            feature_extractor=ConstantFeatureExtractor(value=2.0),
        )


def test_test_derived_threshold_metadata_fails_closed(tmp_path: Path) -> None:
    feature_bank_dir, threshold_path = write_package(tmp_path)
    threshold_artifact = json.loads(threshold_path.read_text(encoding="utf-8"))
    threshold_artifact["calibration"]["uses_test_scores"] = True
    threshold_path.write_text(json.dumps(threshold_artifact), encoding="utf-8")

    with pytest.raises(
        ModelPackageError,
        match="normal validation data only",
    ):
        AnomalyInferenceService(
            feature_bank_dir=feature_bank_dir,
            threshold_artifact_path=threshold_path,
            feature_extractor=ConstantFeatureExtractor(value=2.0),
        )


def test_missing_artifacts_do_not_fall_back(tmp_path: Path) -> None:
    with pytest.raises(
        ModelPackageError,
        match="Feature-bank metadata could not be loaded",
    ):
        AnomalyInferenceService(
            feature_bank_dir=tmp_path / "missing-bank",
            threshold_artifact_path=tmp_path / "missing-threshold.json",
            feature_extractor=ConstantFeatureExtractor(value=2.0),
        )


def test_runtime_preprocessing_dimensions_cannot_drift_from_contract(
    tmp_path: Path,
) -> None:
    feature_bank_dir, threshold_path = write_package(tmp_path)

    with pytest.raises(
        ModelPackageError,
        match="dimensions do not match the production contract",
    ):
        AnomalyInferenceService(
            feature_bank_dir=feature_bank_dir,
            threshold_artifact_path=threshold_path,
            preprocessing_service=ImagePreprocessingService(
                target_width=128,
                target_height=128,
            ),
            feature_extractor=ConstantFeatureExtractor(value=2.0),
        )
