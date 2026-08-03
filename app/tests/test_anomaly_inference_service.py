from pathlib import Path

import pytest
import torch
from PIL import Image

from app.contracts.inference import MODEL_PACKAGE_SCHEMA_VERSION
from app.services.anomaly_inference_service import AnomalyInferenceService
from app.services.image_preprocessing_service import ImagePreprocessingService
from app.services.model_package_loader import (
    ModelPackageCompatibilityError,
    ModelPackageLoader,
)
from app.tests.model_package_fixtures import (
    ConstantFeatureExtractor,
    write_package_fixture,
)


def write_image(path: Path) -> None:
    Image.new("RGB", (16, 16), color=(120, 80, 40)).save(path)


def test_inference_uses_loaded_package_and_strict_threshold(
    tmp_path: Path,
) -> None:
    fixture = write_package_fixture(tmp_path, threshold=2.0)
    image_path = tmp_path / "image.png"
    write_image(image_path)
    extractor = ConstantFeatureExtractor(value=2.0)
    package = ModelPackageLoader(
        package_manifest_path=fixture.manifest_path,
        feature_bank_dir=fixture.feature_bank_dir,
        extractor_factory=lambda device: extractor,
    ).load()
    service = AnomalyInferenceService(package=package)

    equal_result = service.predict(image_path)

    assert equal_result.anomaly_score == pytest.approx(2.0)
    assert equal_result.predicted_label.value == "normal"
    assert equal_result.threshold == pytest.approx(2.0)
    assert equal_result.model_version.startswith("mvtec-tile-resnet18-knn-")
    assert equal_result.model_lineage.schema_version == (MODEL_PACKAGE_SCHEMA_VERSION)
    assert equal_result.model_lineage.dataset_category == "tile"
    assert equal_result.model_lineage.scorer_k == 1
    assert extractor.received_images is not None
    assert extractor.received_images.shape == (1, 3, 224, 224)
    assert extractor.received_images.dtype == torch.float32
    assert extractor.received_images.min().item() >= 0.0
    assert extractor.received_images.max().item() <= 1.0


def test_score_above_loaded_threshold_is_anomalous(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path, threshold=1.9)
    image_path = tmp_path / "image.png"
    write_image(image_path)
    package = ModelPackageLoader(
        package_manifest_path=fixture.manifest_path,
        feature_bank_dir=fixture.feature_bank_dir,
        extractor_factory=lambda device: ConstantFeatureExtractor(value=2.0),
    ).load()

    result = AnomalyInferenceService(package=package).predict(image_path)

    assert result.predicted_label.value == "anomalous"


def test_runtime_preprocessing_dimensions_cannot_drift_from_package_contract(
    tmp_path: Path,
) -> None:
    fixture = write_package_fixture(tmp_path)
    package = ModelPackageLoader(
        package_manifest_path=fixture.manifest_path,
        feature_bank_dir=fixture.feature_bank_dir,
        extractor_factory=lambda device: ConstantFeatureExtractor(),
    ).load()

    with pytest.raises(
        ModelPackageCompatibilityError,
        match="dimensions do not match the production contract",
    ):
        AnomalyInferenceService(
            package=package,
            preprocessing_service=ImagePreprocessingService(
                target_width=128,
                target_height=128,
            ),
        )
