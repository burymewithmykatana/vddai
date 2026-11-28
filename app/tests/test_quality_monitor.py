from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from prometheus_client import CollectorRegistry, generate_latest

from app.contracts.inference import (
    PREPROCESSING_SCHEMA_VERSION,
    AnomalyInferenceResult,
    classify_anomaly_score,
)
from app.services import quality_monitor
from app.services.anomaly_inference_service import AnomalyInferenceService
from app.services.image_preprocessing_service import PreprocessedImage
from app.services.model_package_loader import ModelPackageLoader
from app.services.quality_monitor import (
    WARNING_SIGNALS,
    QualityReference,
    QualityWindow,
    image_quality,
    quality_observer,
    read_quality_reference,
)
from app.tests.model_package_fixtures import (
    ConstantFeatureExtractor,
    write_package_fixture,
)
from app.tests.test_prediction_api import create_model_lineage
from ml.build_quality_reference import build_reference
from ml.data.build_manifest import DatasetManifest, ManifestRecord
from ml.generate_feature_bank import calculate_manifest_fingerprint
from scripts.report_quality_shift import report_from_scrape

PACKAGE = "fixture-model-v1"


def result_for(score: float, package_id: str = PACKAGE) -> AnomalyInferenceResult:
    return AnomalyInferenceResult(
        predicted_label=classify_anomaly_score(score=score, threshold=2),
        anomaly_score=score,
        threshold=2,
        model_version=package_id,
        model_lineage=create_model_lineage(package_id=package_id, threshold=2),
        latency_ms=4,
    )


def reference() -> QualityReference:
    return QualityReference(
        schema_version="vddai.quality_reference.v1",
        source="synthetic_fixture",
        package_id=PACKAGE,
        manifest_fingerprint=result_for(1).model_lineage.manifest_fingerprint,
        preprocessing_version=PREPROCESSING_SCHEMA_VERSION,
        count=30,
        format_counts={"jpeg": 0, "png": 30, "webp": 0, "other": 0},
        pixel_mean=0.25,
        pixel_contrast=0,
        anomaly_count=0,
        score_p95=1,
    )


def image(value: float, second: float, format_name: str) -> PreprocessedImage:
    array = np.array([value, second] * 3, dtype=np.float32).reshape((3, 1, 2))
    return PreprocessedImage(array, 256, 512, 2, 1, format_name)


def scrape_report(window: QualityWindow) -> dict[str, object]:
    registry = CollectorRegistry()
    registry.register(window)
    return report_from_scrape(generate_latest(registry).decode("utf-8"))


def test_controlled_shift_and_private_aggregate_report() -> None:
    window = QualityWindow(reference())
    for _ in range(29):
        window.observe(image(0.25, 0.25, "PNG"), result_for(1))
    small = scrape_report(window)
    assert small["observations"] == 29
    assert small["comparison"] == "unavailable"
    assert small["warnings"] is None

    window.observe(image(0.25, 0.25, "PNG"), result_for(1))
    assert scrape_report(window)["warnings"] == []

    for _ in range(30):
        window.observe(image(0.5, 1, "JPEG"), result_for(3))
    shifted = scrape_report(window)
    assert shifted["package_id"] == PACKAGE
    assert shifted["reference"] == {"synthetic_fixture": 30}
    assert shifted["observations"] == 60
    assert shifted["warnings"] == list(WARNING_SIGNALS)
    assert shifted["image_formats"] == {"jpeg": 30, "png": 30, "webp": 0, "other": 0}
    assert shifted["distribution_bins"]["score"]["4"] == 30
    assert shifted["distribution_bins"]["width"]["256"] == 60
    assert shifted["distribution_bins"]["height"]["512"] == 60


def test_window_bounds_and_model_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 0
    monkeypatch.setattr(quality_monitor.time, "monotonic", lambda: now)
    window = QualityWindow(reference())
    for _ in range(30):
        window.observe(image(0.25, 0.25, "PNG"), result_for(1))
    now = 60
    window.observe(image(0.25, 0.25, "PNG"), result_for(1, "fixture-model-v2"))
    now = 120
    for _ in range(30):
        window.observe(image(0.25, 0.25, "PNG"), result_for(1))
    mixed = scrape_report(window)
    assert mixed["warnings"] is None
    assert mixed["observations"] == 30
    assert mixed["package_id"] == PACKAGE
    now = 62 * 60
    assert scrape_report(window)["observations"] == 0
    for _ in range(30):
        window.observe(image(0.25, 0.25, "PNG"), result_for(1))
    assert scrape_report(window)["warnings"] == []


def test_reference_failure_is_safe(tmp_path: Path) -> None:
    path = tmp_path / "reference.json"
    path.write_text(reference().model_dump_json(), encoding="utf-8")
    assert read_quality_reference(path) is None
    assert read_quality_reference(path, allow_synthetic=True) == reference()
    path.write_text('{"schema_version":"unknown"}', encoding="utf-8")
    assert read_quality_reference(path) is None
    assert read_quality_reference(tmp_path / "missing") is None
    with pytest.raises(ValueError, match="unavailable"):
        report_from_scrape("unrelated_metric 1\n")


def test_frozen_inference_observation_after_latency_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = write_package_fixture(tmp_path / "package")
    package = ModelPackageLoader(
        package_manifest_path=fixture.manifest_path,
        feature_bank_dir=fixture.feature_bank_dir,
        extractor_factory=lambda _: ConstantFeatureExtractor(),
    ).load()
    path = tmp_path / "input.png"
    Image.new("RGB", (13, 9), (64, 64, 64)).save(path)
    service = AnomalyInferenceService(package=package)
    clock = iter([10, 10.005, 100, 100.005])
    monkeypatch.setattr(
        "app.services.anomaly_inference_service.time.perf_counter", lambda: next(clock)
    )
    samples = []

    def observe(image, result):
        samples.append((image_quality(image), result))

    token = quality_observer.set(observe)
    try:
        measured = service.predict(path)
    finally:
        quality_observer.reset(token)
    assert measured == service.predict(path)
    assert measured.latency_ms == 5
    measured_image, _ = samples[0]
    assert measured_image.width == 13 and measured_image.height == 9
    assert measured_image.format == "png"
    assert measured_image.mean == pytest.approx(64 / 255)
    assert measured_image.contrast == 0


@pytest.fixture
def validation_artifacts(tmp_path: Path):
    fixture = write_package_fixture(tmp_path / "package")
    package = ModelPackageLoader(
        package_manifest_path=fixture.manifest_path,
        feature_bank_dir=fixture.feature_bank_dir,
        extractor_factory=lambda _: ConstantFeatureExtractor(),
    ).load()
    data = tmp_path / "dataset"
    normal = data / "train" / "good"
    normal.mkdir(parents=True)
    records = []
    for i in range(30):
        filename = f"{i}.png"
        Image.new("RGB", (8, 8), (64, 64, 64)).save(normal / filename)
        records.append(
            ManifestRecord(
                sample_id=f"normal-{i}",
                image_path=f"train/good/{filename}",
                split="validation",
                label=0,
                class_name="good",
                is_anomaly=False,
                mask_path=None,
                width=8,
                height=8,
                image_format="PNG",
                mode="RGB",
            )
        )
    absent_test_image = replace(
        records[0],
        sample_id="official",
        split="test",
        image_path="test/good/absent.png",
    )
    manifest = DatasetManifest(
        "MVTec AD", "tile", "dataset-v1", 42, 0.2, [*records, absent_test_image]
    )
    return package, manifest, data


def bind_manifest(package, manifest):
    return replace(
        package,
        lineage=package.lineage.model_copy(
            update={"manifest_fingerprint": calculate_manifest_fingerprint(manifest)}
        ),
    )


def test_reference_replays_only_matched_normal_validation(validation_artifacts) -> None:
    package, manifest, data = validation_artifacts
    bound = bind_manifest(package, manifest)
    result = build_reference(bound, manifest, data)
    assert result.count == 30
    assert result.anomaly_count == 0
    assert result.score_p95 == 2

    mislabeled = replace(manifest.records[-1], split="validation")
    wrong_split = replace(manifest, records=[*manifest.records[:-1], mislabeled])
    with pytest.raises(ValueError, match="does not match"):
        build_reference(bound, wrong_split, data)
    with pytest.raises(ValueError, match="outside the normal split"):
        build_reference(bind_manifest(package, wrong_split), wrong_split, data)


@pytest.mark.parametrize(
    ("sample_id", "path", "message"),
    [
        ("normal-0", "train/good/missing.png", "Duplicate manifest sample identity"),
        ("train-extra", "train/good/0.png", "Duplicate manifest image path"),
        ("train-extra", "train/./good/0.png", "Duplicate manifest image path"),
    ],
)
def test_reference_rejects_overlapping_train_and_validation(
    validation_artifacts, sample_id, path, message
) -> None:
    package, manifest, data = validation_artifacts
    train = replace(
        manifest.records[0], sample_id=sample_id, image_path=path, split="train"
    )
    overlapping = replace(manifest, records=[*manifest.records, train])
    with pytest.raises(ValueError, match=message):
        build_reference(bind_manifest(package, overlapping), overlapping, data)
    assert package.feature_extractor.extract_calls == 0


def test_reference_rejects_decoded_mode_mismatch(validation_artifacts) -> None:
    package, manifest, data = validation_artifacts
    Image.new("L", (8, 8), 192).save(data / manifest.records[0].image_path)
    with pytest.raises(ValueError, match="Validation image metadata differs"):
        build_reference(bind_manifest(package, manifest), manifest, data)
