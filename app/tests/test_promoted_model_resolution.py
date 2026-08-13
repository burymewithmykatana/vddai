"""Integration coverage for registry-selected serving and safe rollback."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.contracts.model_registry import (
    ModelCandidate,
    ModelStage,
    PromotionCriteria,
    SmokeInferenceEvidence,
    build_model_version,
)
from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.prediction import Prediction, PredictionStatus
from app.models.user import User
from app.services import model_package_loader
from app.services.anomaly_inference_service import (
    reset_anomaly_inference_service_cache_for_tests,
)
from app.services.model_package_loader import (
    ModelPackageLoader,
    ProductionModelPackage,
    reset_model_package_cache_for_tests,
)
from app.services.model_registry import ModelRegistry
from app.services.promoted_model_resolver import (
    PromotedModelResolutionError,
    PromotedModelResolver,
)
from app.tests.model_package_fixtures import (
    ConstantFeatureExtractor,
    PackageFixture,
    sha256_file,
    write_package_fixture,
)
from app.workers.prediction_worker import process_next_prediction

CRITERIA = PromotionCriteria(minimum_metrics={"validation_threshold_f1": 0.80})


def _load(fixture: PackageFixture) -> ProductionModelPackage:
    return ModelPackageLoader(
        package_manifest_path=fixture.manifest_path,
        feature_bank_dir=fixture.feature_bank_dir,
        extractor_factory=lambda _device: ConstantFeatureExtractor(),
    ).load()


def _candidate(
    root: Path,
    fixture: PackageFixture,
    package: ProductionModelPackage,
    run_id: str,
) -> ModelCandidate:
    manifest_sha256 = sha256_file(fixture.manifest_path)
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
        code_revision="b" * 40,
        metrics={"values": {"validation_threshold_f1": 0.95}},
        registered_by="ml-owner@example.test",
        registered_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )


def _smoke(package: ProductionModelPackage) -> SmokeInferenceEvidence:
    return SmokeInferenceEvidence(
        package_id=package.package_id,
        anomaly_score=0.0,
        threshold=package.threshold,
        predicted_label="normal",
    )


def _promote(
    registry: ModelRegistry,
    candidate: ModelCandidate,
    package: ProductionModelPackage,
    environment: ModelStage,
) -> None:
    registry.promote(
        candidate.model_version,
        environment=environment,
        requested_by="release-owner@example.test",
        reason=f"Integration test {environment.value} selection",
        criteria=CRITERIA,
        package_validator=lambda _candidate: package,
        smoke_inference=_smoke,
    )


def _queue_prediction(db: Session, *, user_id: int, image_path: Path) -> Prediction:
    prediction = Prediction(
        user_id=user_id,
        image_path=str(image_path),
        image_format="PNG",
        image_width=16,
        image_height=16,
        status=PredictionStatus.QUEUED.value,
    )
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    return prediction


def test_resolver_fails_closed_without_production_selection(tmp_path: Path) -> None:
    registry = ModelRegistry(
        tmp_path / "registry.sqlite3",
        repository_root=tmp_path,
    )

    with pytest.raises(PromotedModelResolutionError, match="No production"):
        PromotedModelResolver(
            registry.database_path,
            repository_root=tmp_path,
        ).resolve()


def test_health_model_exposes_identity_without_internal_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = write_package_fixture(tmp_path / "candidate")
    package = _load(fixture)
    candidate = _candidate(tmp_path, fixture, package, "run-health")
    registry = ModelRegistry(tmp_path / "registry.sqlite3", repository_root=tmp_path)
    registry.register_candidate(candidate)
    _promote(registry, candidate, package, ModelStage.STAGING)
    _promote(registry, candidate, package, ModelStage.PRODUCTION)
    monkeypatch.setattr(settings, "MODEL_REGISTRY_PATH", str(registry.database_path))
    monkeypatch.setattr(settings, "MODEL_ARTIFACT_ROOT", str(tmp_path))

    with TestClient(app) as client:
        response = client.get("/health/model")

    assert response.status_code == 200
    assert response.json() == {
        "status": "selected",
        "model_version": candidate.model_version,
        "package_id": candidate.package_id,
    }
    assert str(tmp_path) not in response.text
    assert "feature_bank" not in response.text


def test_health_model_returns_safe_unavailable_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        settings,
        "MODEL_REGISTRY_PATH",
        str(tmp_path / "missing.sqlite3"),
    )
    monkeypatch.setattr(settings, "MODEL_ARTIFACT_ROOT", str(tmp_path))

    with TestClient(app) as client:
        response = client.get("/health/model")

    assert response.status_code == 503
    assert response.json() == {"detail": "production_model_unavailable"}
    assert str(tmp_path) not in response.text


def test_worker_follows_promotion_and_rollback_without_restart(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    fixture_a = write_package_fixture(tmp_path / "candidate-a", threshold=2.0)
    fixture_b = write_package_fixture(tmp_path / "candidate-b", threshold=3.0)
    package_a = _load(fixture_a)
    package_b = _load(fixture_b)
    candidate_a = _candidate(tmp_path, fixture_a, package_a, "run-a")
    candidate_b = _candidate(tmp_path, fixture_b, package_b, "run-b")
    registry = ModelRegistry(tmp_path / "registry.sqlite3", repository_root=tmp_path)
    registry.register_candidate(candidate_a)
    registry.register_candidate(candidate_b)
    _promote(registry, candidate_a, package_a, ModelStage.STAGING)
    _promote(registry, candidate_a, package_a, ModelStage.PRODUCTION)
    monkeypatch.setattr(settings, "MODEL_REGISTRY_PATH", str(registry.database_path))
    monkeypatch.setattr(settings, "MODEL_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        model_package_loader,
        "_load_cached_resnet18_extractor",
        lambda _device: ConstantFeatureExtractor(),
    )
    reset_anomaly_inference_service_cache_for_tests()
    reset_model_package_cache_for_tests()

    try:
        user = User(
            email="registry-worker@example.test",
            hashed_password="not-a-real-password",
            is_active=True,
            is_admin=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        image_path = tmp_path / "tile.png"
        Image.new("RGB", (16, 16), color=(120, 80, 40)).save(image_path)

        first = _queue_prediction(db, user_id=user.id, image_path=image_path)
        assert process_next_prediction(db) is True
        db.expire_all()
        assert db.get(Prediction, first.id).model_version == candidate_a.package_id

        _promote(registry, candidate_b, package_b, ModelStage.STAGING)
        _promote(registry, candidate_b, package_b, ModelStage.PRODUCTION)
        second = _queue_prediction(db, user_id=user.id, image_path=image_path)
        assert process_next_prediction(db) is True
        db.expire_all()
        assert db.get(Prediction, second.id).model_version == candidate_b.package_id

        registry.rollback(
            environment=ModelStage.PRODUCTION,
            requested_by="release-owner@example.test",
            reason="Integration test rollback",
            criteria=CRITERIA,
            package_validator=lambda candidate: (
                package_a
                if candidate.model_version == candidate_a.model_version
                else package_b
            ),
            smoke_inference=_smoke,
        )
        third = _queue_prediction(db, user_id=user.id, image_path=image_path)
        assert process_next_prediction(db) is True
        db.expire_all()
        assert db.get(Prediction, third.id).model_version == candidate_a.package_id
    finally:
        db.close()
        reset_anomaly_inference_service_cache_for_tests()
        reset_model_package_cache_for_tests()
        Base.metadata.drop_all(bind=engine)
