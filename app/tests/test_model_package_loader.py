from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pytest

from app.core.config import settings
from app.services import model_package_loader
from app.services.model_package_loader import (
    ModelPackageArtifactError,
    ModelPackageChecksumError,
    ModelPackageCompatibilityError,
    ModelPackageInitializationError,
    ModelPackageLoader,
    ProductionModelPackage,
    get_production_model_package,
    reset_model_package_cache_for_tests,
)
from app.services.promoted_model_resolver import PromotedModelSelection
from app.tests.model_package_fixtures import (
    ConstantFeatureExtractor,
    PackageFixture,
    read_json,
    sha256_file,
    write_json,
    write_package_fixture,
)

pytestmark = pytest.mark.w7_production_gate


def create_loader(
    package: PackageFixture,
    *,
    extractor_factory=None,
) -> ModelPackageLoader:
    return ModelPackageLoader(
        package_manifest_path=package.manifest_path,
        feature_bank_dir=package.feature_bank_dir,
        extractor_factory=extractor_factory
        or (lambda device: ConstantFeatureExtractor()),
    )


def test_valid_package_is_immutable_initialized_and_ready_to_score(
    tmp_path: Path,
) -> None:
    fixture = write_package_fixture(tmp_path)

    package = create_loader(fixture).load()

    assert isinstance(package, ProductionModelPackage)
    assert package.threshold == pytest.approx(2.0)
    assert package.scorer.bank_size == 2
    assert package.scorer.feature_dimension == 512
    assert package.scorer.k == 1
    assert package.lineage.package_id == package.package_id
    assert package.lineage.feature_bank_sha256 == sha256_file(fixture.features_path)
    assert package.lineage.threshold_artifact_sha256 == sha256_file(
        fixture.threshold_path
    )
    with pytest.raises(FrozenInstanceError):
        package.threshold = 3.0  # type: ignore[misc]


def test_missing_required_file_fails_explicitly(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path)
    fixture.threshold_path.unlink()

    with pytest.raises(
        ModelPackageArtifactError,
        match="Promoted threshold artifact is missing",
    ):
        create_loader(fixture).load()


def test_malformed_json_fails_explicitly(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path)
    fixture.manifest_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(
        ModelPackageArtifactError,
        match="contains malformed JSON",
    ):
        create_loader(fixture).load()


def test_unsupported_schema_fails_closed(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path)
    manifest = read_json(fixture.manifest_path)
    manifest["schema_version"] = "vddai.image_evaluation.v999"
    write_json(fixture.manifest_path, manifest)

    with pytest.raises(
        ModelPackageCompatibilityError,
        match="Unsupported package run-manifest schema",
    ):
        create_loader(fixture).load()


def test_manifest_member_path_cannot_escape_package_root(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path)
    manifest = read_json(fixture.manifest_path)
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, dict)
    threshold_file = artifacts["threshold.json"]
    assert isinstance(threshold_file, dict)
    threshold_file["path"] = "../../outside/threshold.json"
    write_json(fixture.manifest_path, manifest)

    with pytest.raises(
        ModelPackageArtifactError,
        match="escapes its configured artifact root",
    ):
        create_loader(fixture).load()


def test_feature_bank_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path)
    with fixture.features_path.open("ab") as feature_file:
        feature_file.write(b"corruption")

    with pytest.raises(
        ModelPackageChecksumError,
        match="Feature-bank archive checksum does not match",
    ):
        create_loader(fixture).load()


def test_incompatible_preprocessing_image_size_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = write_package_fixture(tmp_path)
    metadata_path = fixture.feature_bank_dir / "metadata.json"
    metadata = read_json(metadata_path)
    metadata["image_size"] = {"height": 128, "width": 128}
    write_json(metadata_path, metadata)

    with pytest.raises(
        ModelPackageCompatibilityError,
        match="image size does not match preprocessing contract",
    ):
        create_loader(fixture).load()


def test_extractor_lineage_mismatch_fails_closed(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path)
    metadata_path = fixture.feature_bank_dir / "metadata.json"
    metadata = read_json(metadata_path)
    extractor = metadata["feature_extractor"]
    assert isinstance(extractor, dict)
    extractor["feature_layer"] = "layer4"
    write_json(metadata_path, metadata)

    with pytest.raises(
        ModelPackageCompatibilityError,
        match="extractor lineage is incompatible",
    ):
        create_loader(fixture).load()


def test_feature_dimension_mismatch_fails_closed(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path)
    np.savez_compressed(
        fixture.features_path,
        features=np.zeros((2, 511), dtype=np.float32),
        sample_ids=np.asarray(["normal-1", "normal-2"], dtype=np.str_),
        source_paths=np.asarray(["a.png", "b.png"], dtype=np.str_),
        splits=np.asarray(["train", "train"], dtype=np.str_),
        dataset_versions=np.asarray(["dataset-v1", "dataset-v1"]),
    )
    metadata_path = fixture.feature_bank_dir / "metadata.json"
    metadata = read_json(metadata_path)
    files = metadata["files"]
    assert isinstance(files, dict)
    feature_file = files["features"]
    assert isinstance(feature_file, dict)
    feature_file["sha256"] = sha256_file(fixture.features_path)
    write_json(metadata_path, metadata)

    with pytest.raises(
        ModelPackageCompatibilityError,
        match="feature matrix violates the frozen dimension",
    ):
        create_loader(fixture).load()


def test_invalid_k_larger_than_bank_fails_closed(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path, scorer_k=3)

    with pytest.raises(
        ModelPackageCompatibilityError,
        match="scorer k exceeds the feature-bank size",
    ):
        create_loader(fixture).load()


def test_non_finite_threshold_fails_closed(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path)
    threshold = read_json(fixture.threshold_path)
    selection = threshold["threshold_selection"]
    assert isinstance(selection, dict)
    selection["threshold"] = float("nan")
    write_json(fixture.threshold_path, threshold)
    fixture.refresh_threshold_checksum()

    with pytest.raises(
        ModelPackageCompatibilityError,
        match="Threshold selection metadata is incompatible",
    ):
        create_loader(fixture).load()


def test_incompatible_decision_semantics_fail_before_initialization(
    tmp_path: Path,
) -> None:
    fixture = write_package_fixture(tmp_path)
    threshold = read_json(fixture.threshold_path)
    threshold["prediction_semantics"] = {
        "anomalous": "score >= threshold",
        "normal": "score < threshold",
    }
    write_json(fixture.threshold_path, threshold)
    fixture.refresh_threshold_checksum()
    factory_calls = 0

    def extractor_factory(device: str) -> ConstantFeatureExtractor:
        nonlocal factory_calls
        factory_calls += 1
        return ConstantFeatureExtractor()

    with pytest.raises(
        ModelPackageCompatibilityError,
        match="prediction semantics are incompatible",
    ):
        create_loader(
            fixture,
            extractor_factory=extractor_factory,
        ).load()
    assert factory_calls == 0


def test_test_derived_threshold_fails_closed(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path)
    threshold = read_json(fixture.threshold_path)
    calibration = threshold["calibration"]
    assert isinstance(calibration, dict)
    calibration["uses_test_scores"] = True
    write_json(fixture.threshold_path, threshold)
    fixture.refresh_threshold_checksum()

    with pytest.raises(
        ModelPackageCompatibilityError,
        match="normal validation data only",
    ):
        create_loader(fixture).load()


def test_runtime_initialization_failure_returns_no_partial_package(
    tmp_path: Path,
) -> None:
    fixture = write_package_fixture(tmp_path)

    def broken_extractor_factory(device: str) -> ConstantFeatureExtractor:
        raise RuntimeError("simulated checkpoint failure")

    with pytest.raises(
        ModelPackageInitializationError,
        match="could not be initialized",
    ):
        create_loader(
            fixture,
            extractor_factory=broken_extractor_factory,
        ).load()


def test_run_manifest_lineage_must_match_serving_artifacts(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path)
    manifest = read_json(fixture.manifest_path)
    lineage = manifest["lineage"]
    assert isinstance(lineage, dict)
    dataset = lineage["dataset"]
    assert isinstance(dataset, dict)
    dataset["version"] = "different-dataset"
    write_json(fixture.manifest_path, manifest)

    with pytest.raises(
        ModelPackageCompatibilityError,
        match="incompatible lineage",
    ):
        create_loader(fixture).load()


def test_cached_package_initializes_once_per_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_package_fixture(tmp_path)
    loaded_package = create_loader(fixture).load()
    load_calls = 0

    def fake_load(self: ModelPackageLoader) -> ProductionModelPackage:
        nonlocal load_calls
        load_calls += 1
        return loaded_package

    reset_model_package_cache_for_tests()
    monkeypatch.setattr(model_package_loader.ModelPackageLoader, "load", fake_load)
    selection = PromotedModelSelection(
        model_version="registry-version-a",
        package_id=loaded_package.package_id,
        package_manifest_path=fixture.manifest_path.resolve(),
        package_manifest_sha256=sha256_file(fixture.manifest_path),
        feature_bank_dir=fixture.feature_bank_dir.resolve(),
        feature_bank_sha256=loaded_package.lineage.feature_bank_sha256,
        dataset_name=loaded_package.lineage.dataset_name,
        dataset_category=loaded_package.lineage.dataset_category,
        dataset_version=loaded_package.lineage.dataset_version,
        manifest_fingerprint=loaded_package.lineage.manifest_fingerprint,
    )
    monkeypatch.setattr(
        model_package_loader,
        "resolve_production_model_selection",
        lambda: selection,
    )

    first = get_production_model_package()
    second = get_production_model_package()

    assert first is loaded_package
    assert second is loaded_package
    assert load_calls == 1
    reset_model_package_cache_for_tests()
