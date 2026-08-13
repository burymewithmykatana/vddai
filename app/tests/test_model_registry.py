"""Regression coverage for candidate registration, promotion, and rollback."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.model_registry import (
    ModelCandidate,
    ModelStage,
    PromotionCriteria,
    SmokeInferenceEvidence,
    build_model_version,
)
from app.services.model_package_loader import (
    ModelPackageLoader,
    ProductionModelPackage,
)
from app.services.model_registry import (
    ModelRegistry,
    ModelRegistryError,
    PromotionRejectedError,
)
from app.tests.model_package_fixtures import (
    ConstantFeatureExtractor,
    PackageFixture,
    sha256_file,
    write_package_fixture,
)

CRITERIA = PromotionCriteria(
    minimum_metrics={
        "test_roc_auc": 0.90,
        "test_average_precision": 0.90,
        "test_threshold_f1": 0.80,
    }
)


def _load_package(fixture: PackageFixture) -> ProductionModelPackage:
    return ModelPackageLoader(
        package_manifest_path=fixture.manifest_path,
        feature_bank_dir=fixture.feature_bank_dir,
        extractor_factory=lambda _device: ConstantFeatureExtractor(),
    ).load()


def _candidate(
    root: Path,
    fixture: PackageFixture,
    package: ProductionModelPackage,
    *,
    run_id: str,
    metric_override: dict[str, float] | None = None,
) -> ModelCandidate:
    manifest_sha256 = sha256_file(fixture.manifest_path)
    metrics = {
        "test_roc_auc": 0.98,
        "test_average_precision": 0.97,
        "test_threshold_f1": 0.91,
    }
    metrics.update(metric_override or {})
    return ModelCandidate(
        model_version=build_model_version(
            package_id=package.package_id,
            package_manifest_sha256=manifest_sha256,
        ),
        package_id=package.package_id,
        experiment_run_id=run_id,
        package_manifest_path=fixture.manifest_path.relative_to(root).as_posix(),
        package_manifest_sha256=manifest_sha256,
        feature_bank_dir=fixture.feature_bank_dir.relative_to(root).as_posix(),
        feature_bank_sha256=package.lineage.feature_bank_sha256,
        dataset_name=package.lineage.dataset_name,
        dataset_category=package.lineage.dataset_category,
        dataset_version=package.lineage.dataset_version,
        manifest_fingerprint=package.lineage.manifest_fingerprint,
        code_revision="a" * 40,
        metrics={"values": metrics},
        registered_by="ml-owner@example.test",
        registered_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )


def _smoke(package: ProductionModelPackage) -> SmokeInferenceEvidence:
    score = float(package.scorer.score([[0.0] * package.lineage.feature_dimension])[0])
    return SmokeInferenceEvidence(
        package_id=package.package_id,
        anomaly_score=score,
        threshold=package.threshold,
        predicted_label="anomalous" if score > package.threshold else "normal",
    )


def test_registration_is_immutable_and_starts_as_candidate(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path / "candidate-a")
    package = _load_package(fixture)
    candidate = _candidate(tmp_path, fixture, package, run_id="run-a")
    registry = ModelRegistry(tmp_path / "registry.sqlite3", repository_root=tmp_path)

    registry.register_candidate(candidate)

    assert registry.get_candidate(candidate.model_version) == candidate
    assert registry.get_stage(candidate.model_version) is ModelStage.CANDIDATE
    with pytest.raises(ModelRegistryError, match="immutable"):
        registry.register_candidate(candidate)


def test_candidate_requires_derived_immutable_version(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path / "candidate-a")
    package = _load_package(fixture)
    candidate = _candidate(tmp_path, fixture, package, run_id="run-a")

    with pytest.raises(ValidationError, match="immutable naming rule"):
        ModelCandidate.model_validate(
            {**candidate.model_dump(), "model_version": "wrong-version"}
        )


def test_registration_rejects_manifest_checksum_tampering(tmp_path: Path) -> None:
    fixture = write_package_fixture(tmp_path / "candidate-a")
    package = _load_package(fixture)
    candidate = _candidate(tmp_path, fixture, package, run_id="run-a")
    fixture.manifest_path.write_text("{}", encoding="utf-8")
    registry = ModelRegistry(tmp_path / "registry.sqlite3", repository_root=tmp_path)

    with pytest.raises(ModelRegistryError, match="checksum"):
        registry.register_candidate(candidate)


def test_production_requires_exact_staged_version_and_records_rejection(
    tmp_path: Path,
) -> None:
    fixture = write_package_fixture(tmp_path / "candidate-a")
    package = _load_package(fixture)
    candidate = _candidate(tmp_path, fixture, package, run_id="run-a")
    registry = ModelRegistry(tmp_path / "registry.sqlite3", repository_root=tmp_path)
    registry.register_candidate(candidate)

    with pytest.raises(PromotionRejectedError) as caught:
        registry.promote(
            candidate.model_version,
            environment=ModelStage.PRODUCTION,
            requested_by="release-owner@example.test",
            reason="Release candidate approval",
            criteria=CRITERIA,
            package_validator=lambda _candidate: package,
            smoke_inference=_smoke,
        )

    attempt = registry.get_attempt(caught.value.attempt_id)
    assert attempt["outcome"] == "rejected"
    assert attempt["previous_version"] is None
    assert attempt["checks"]["package_validation"] == "passed"
    assert "requires the exact version" in attempt["rejection_reasons"][0]
    assert registry.get_environment(ModelStage.PRODUCTION)["active_version"] is None


def test_metric_and_package_failures_are_audited_without_state_change(
    tmp_path: Path,
) -> None:
    fixture = write_package_fixture(tmp_path / "candidate-a")
    package = _load_package(fixture)
    candidate = _candidate(
        tmp_path,
        fixture,
        package,
        run_id="run-a",
        metric_override={"test_threshold_f1": 0.50},
    )
    registry = ModelRegistry(tmp_path / "registry.sqlite3", repository_root=tmp_path)
    registry.register_candidate(candidate)

    with pytest.raises(PromotionRejectedError) as caught:
        registry.promote(
            candidate.model_version,
            environment=ModelStage.STAGING,
            requested_by="release-owner@example.test",
            reason="Exercise rejection path",
            criteria=CRITERIA,
            package_validator=lambda _candidate: (_ for _ in ()).throw(
                RuntimeError("unsafe internal detail")
            ),
            smoke_inference=_smoke,
        )

    attempt = registry.get_attempt(caught.value.attempt_id)
    assert attempt["outcome"] == "rejected"
    assert len(attempt["rejection_reasons"]) == 2
    assert "unsafe internal detail" not in str(attempt)
    assert registry.get_stage(candidate.model_version) is ModelStage.CANDIDATE


def test_promotions_capture_rollback_target_and_rollback_is_safe(
    tmp_path: Path,
) -> None:
    fixture_a = write_package_fixture(tmp_path / "candidate-a", threshold=2.0)
    fixture_b = write_package_fixture(tmp_path / "candidate-b", threshold=3.0)
    package_a = _load_package(fixture_a)
    package_b = _load_package(fixture_b)
    candidate_a = _candidate(tmp_path, fixture_a, package_a, run_id="run-a")
    candidate_b = _candidate(tmp_path, fixture_b, package_b, run_id="run-b")
    packages = {
        candidate_a.model_version: package_a,
        candidate_b.model_version: package_b,
    }
    registry = ModelRegistry(tmp_path / "registry.sqlite3", repository_root=tmp_path)
    registry.register_candidate(candidate_a)
    registry.register_candidate(candidate_b)
    validator = lambda candidate: packages[candidate.model_version]

    for environment in (ModelStage.STAGING, ModelStage.PRODUCTION):
        registry.promote(
            candidate_a.model_version,
            environment=environment,
            requested_by="release-owner@example.test",
            reason=f"Approve A for {environment.value}",
            criteria=CRITERIA,
            package_validator=validator,
            smoke_inference=_smoke,
        )
    registry.promote(
        candidate_b.model_version,
        environment=ModelStage.STAGING,
        requested_by="release-owner@example.test",
        reason="Stage B",
        criteria=CRITERIA,
        package_validator=validator,
        smoke_inference=_smoke,
    )
    promotion_attempt = registry.promote(
        candidate_b.model_version,
        environment=ModelStage.PRODUCTION,
        requested_by="release-owner@example.test",
        reason="Promote B",
        criteria=CRITERIA,
        package_validator=validator,
        smoke_inference=_smoke,
    )

    production = registry.get_environment(ModelStage.PRODUCTION)
    assert production["active_version"] == candidate_b.model_version
    assert production["rollback_version"] == candidate_a.model_version
    assert (
        registry.get_attempt(promotion_attempt)["previous_version"]
        == candidate_a.model_version
    )

    rollback_attempt = registry.rollback(
        environment=ModelStage.PRODUCTION,
        requested_by="release-owner@example.test",
        reason="Observed release regression",
        criteria=CRITERIA,
        package_validator=validator,
        smoke_inference=_smoke,
    )

    production = registry.get_environment(ModelStage.PRODUCTION)
    assert production["active_version"] == candidate_a.model_version
    assert production["rollback_version"] == candidate_b.model_version
    assert registry.get_attempt(rollback_attempt)["action"] == "rollback"
    assert registry.get_attempt(rollback_attempt)["outcome"] == "approved"
