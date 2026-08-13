from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.contracts.inference import (
    INFERENCE_CONTRACT_SCHEMA_VERSION,
    MODEL_PACKAGE_SCHEMA_VERSION,
    PREPROCESSING_SCHEMA_VERSION,
    AnomalyInferenceResult,
    InferencePackageLineage,
    PredictionFailureCode,
    PredictionLabel,
)
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.prediction import Prediction, PredictionStatus
from app.models.user import User
from app.services.anomaly_inference_service import (
    AnomalyInferenceService,
    reset_anomaly_inference_service_cache_for_tests,
)
from app.services.image_storage_service import image_storage_service
from app.services.model_package_loader import (
    ModelPackageLoader,
    reset_model_package_cache_for_tests,
)
from app.tests.model_package_fixtures import (
    ConstantFeatureExtractor,
    write_package_fixture,
)
from app.workers import prediction_worker
from app.workers.prediction_worker import process_next_prediction, run_forever


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    token = create_access_token(subject=test_user.id)

    return {
        "Authorization": f"Bearer {token}",
    }


@pytest.fixture(autouse=True)
def reset_database():
    """Give every test a clean database."""

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    yield

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client():
    def override_get_db():
        session = SessionLocal()

        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db: Session) -> User:
    user = User(
        email="test@example.com",
        hashed_password="not-a-real-password",
        full_name="Test User",
        is_active=True,
        is_admin=False,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def create_queued_prediction(db: Session, user_id: int) -> Prediction:
    prediction = Prediction(
        user_id=user_id,
        image_path="uploads/test_image_001.jpg",
        image_format="JPEG",
        image_width=16,
        image_height=16,
        status=PredictionStatus.QUEUED.value,
    )

    db.add(prediction)
    db.commit()
    db.refresh(prediction)

    return prediction


def create_model_lineage(
    *,
    package_id: str,
    threshold: float,
) -> InferencePackageLineage:
    return InferencePackageLineage(
        contract_schema_version=INFERENCE_CONTRACT_SCHEMA_VERSION,
        schema_version=MODEL_PACKAGE_SCHEMA_VERSION,
        package_id=package_id,
        preprocessing_schema_version=PREPROCESSING_SCHEMA_VERSION,
        dataset_name="MVTec AD",
        dataset_category="tile",
        dataset_version="dataset-v1",
        manifest_fingerprint=f"sha256:{'a' * 64}",
        feature_bank_schema_version="vddai.feature_bank.v1",
        feature_bank_code_version="vddai.feature_bank.generator.v1",
        feature_bank_path="features.npz",
        feature_bank_sha256=f"sha256:{'b' * 64}",
        feature_bank_sample_count=2,
        extractor_name="torchvision.resnet18",
        extractor_weights="IMAGENET1K_V1",
        extractor_layer="avgpool",
        feature_dimension=512,
        scorer_distance="euclidean",
        scorer_aggregation="mean_k_nearest",
        scorer_k=1,
        threshold_policy="normal_validation_quantile",
        threshold_quantile=0.95,
        threshold_value=threshold,
        threshold_artifact_sha256=f"sha256:{'c' * 64}",
    )


def test_root_endpoint(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "visual defect AI backend is running.",
        "docs": "/docs",
    }


def test_health_check(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ok"
    assert data["service"] == "vddai-backend"
    assert data["environment"] == "test"


@pytest.mark.w6_inference_gate
def test_registered_user_can_login_and_access_authenticated_predictions(
    client: TestClient,
) -> None:
    credentials = {
        "email": "w6-auth@example.com",
        "password": "W6-authentication-password!",
    }

    register_response = client.post(
        "/auth/register",
        json={**credentials, "full_name": "W6 Auth Gate"},
    )
    assert register_response.status_code == 201
    assert register_response.json()["email"] == credentials["email"]

    login_response = client.post("/auth/login", json=credentials)
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]
    assert login_response.json()["token_type"] == "bearer"

    history_response = client.get(
        "/predictions",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert history_response.status_code == 200
    assert history_response.json() == []


@pytest.mark.w6_inference_gate
@pytest.mark.parametrize(
    "password",
    ["short", "é" * 40],
)
def test_registration_rejects_passwords_outside_bcrypt_contract(
    client: TestClient,
    password: str,
) -> None:
    response = client.post(
        "/auth/register",
        json={
            "email": "invalid-password@example.com",
            "password": password,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]


def test_create_prediction_job(
    client: TestClient,
    db: Session,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    with TemporaryDirectory(
        prefix="vddai-test-uploads-",
        dir=".",
    ) as temporary_directory:
        upload_directory = Path(temporary_directory)

        monkeypatch.setattr(
            image_storage_service,
            "upload_directory",
            upload_directory,
        )
        image_contents = create_image_bytes("JPEG")

        response = client.post(
            "/predictions",
            headers=auth_headers,
            files=image_upload(content=image_contents),
        )

        assert response.status_code == 202

        data = response.json()

        assert data["prediction_id"] > 0
        assert data["status"] == PredictionStatus.QUEUED.value
        assert data["message"] == "Prediction job queued successfully."

        prediction = db.get(Prediction, data["prediction_id"])

        assert prediction is not None
        assert prediction.user_id == test_user.id
        assert prediction.image_path.startswith(upload_directory.as_posix())
        assert prediction.image_path.endswith(".jpg")

        stored_image = Path(prediction.image_path)

        assert stored_image.exists()
        assert stored_image.read_bytes() == image_contents


def test_create_prediction_commit_failure_removes_orphaned_upload(
    client: TestClient,
    db: Session,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upload_directory = tmp_path / "uploads"
    monkeypatch.setattr(
        image_storage_service,
        "upload_directory",
        upload_directory,
    )
    failing_session = SessionLocal()

    def fail_commit() -> None:
        raise SQLAlchemyError("simulated queue commit failure")

    monkeypatch.setattr(failing_session, "commit", fail_commit)

    def override_get_db():
        yield failing_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with pytest.raises(SQLAlchemyError, match="queue commit failure"):
            client.post(
                "/predictions",
                headers=auth_headers,
                files=image_upload(),
            )
    finally:
        failing_session.close()

    assert upload_directory.exists()
    assert list(upload_directory.iterdir()) == []
    assert db.query(Prediction).count() == 0


def test_create_prediction_requires_authentication(
    client: TestClient,
):
    response = client.post(
        "/predictions",
        files=image_upload(),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Could not validate authentication credentials."
    )


def test_create_prediction_requires_image(
    client: TestClient,
    auth_headers: dict[str, str],
):
    response = client.post(
        "/predictions",
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_get_prediction_job(
    client: TestClient,
    db: Session,
    test_user: User,
    auth_headers: dict[str, str],
):
    prediction = create_queued_prediction(db, test_user.id)

    response = client.get(
        f"/predictions/{prediction.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == prediction.id
    assert data["user_id"] == test_user.id
    assert data["status"] == PredictionStatus.QUEUED.value
    assert data["predicted_label"] is None
    assert data["confidence"] is None
    assert data["processing_started_at"] is None
    assert data["completed_at"] is None
    assert data["failure_code"] is None
    assert "image_path" not in data
    assert "error_message" not in data


def test_get_missing_prediction_job(
    client: TestClient,
    auth_headers: dict[str, str],
):
    response = client.get(
        "/predictions/9999",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Prediction job not found."


def test_prediction_history_is_owner_scoped_and_newest_first(
    client: TestClient,
    db: Session,
    test_user: User,
    auth_headers: dict[str, str],
):
    first = create_queued_prediction(db, test_user.id)
    second = create_queued_prediction(db, test_user.id)
    other_user = User(
        email="history-other@example.com",
        hashed_password="not-a-real-password",
        is_active=True,
        is_admin=False,
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)
    create_queued_prediction(db, other_user.id)

    response = client.get("/predictions", headers=auth_headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [second.id, first.id]


def test_completed_prediction_read_includes_score_and_lineage(
    client: TestClient,
    db: Session,
    test_user: User,
    auth_headers: dict[str, str],
):
    prediction = create_queued_prediction(db, test_user.id)
    prediction.status = PredictionStatus.COMPLETED.value
    prediction.predicted_label = "normal"
    prediction.anomaly_score = 4.2
    prediction.threshold = 4.2
    prediction.model_version = "package-read-v1"
    prediction.model_lineage = create_model_lineage(
        package_id="package-read-v1",
        threshold=4.2,
    ).model_dump(mode="json")
    prediction.latency_ms = 10
    prediction.processing_started_at = prediction.created_at
    prediction.completed_at = prediction.created_at
    db.commit()

    response = client.get(
        f"/predictions/{prediction.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["predicted_label"] == "normal"
    assert response.json()["anomaly_score"] == pytest.approx(4.2)
    assert response.json()["threshold"] == pytest.approx(4.2)
    assert response.json()["model_version"] == "package-read-v1"
    assert response.json()["processing_started_at"] is not None
    assert response.json()["completed_at"] is not None
    assert response.json()["model_lineage"]["feature_bank_sha256"] == (
        f"sha256:{'b' * 64}"
    )
    assert response.json()["confidence"] is None
    assert "image_path" not in response.json()
    assert "error_message" not in response.json()


def test_worker_completes_queued_prediction(
    db: Session,
    test_user: User,
):
    prediction = create_queued_prediction(db, test_user.id)

    class DeterministicInferenceService:
        def predict(self, image_path: str) -> AnomalyInferenceResult:
            assert image_path == "uploads/test_image_001.jpg"
            with SessionLocal() as inspection_session:
                processing = inspection_session.get(Prediction, prediction.id)
                assert processing is not None
                assert processing.status == PredictionStatus.PROCESSING.value
                assert processing.predicted_label is None
                assert processing.anomaly_score is None
                assert processing.error_message is None
                assert processing.processing_started_at is not None
                assert processing.processing_started_at.tzinfo is None
                assert processing.completed_at is None
            return AnomalyInferenceResult(
                predicted_label=PredictionLabel.ANOMALOUS,
                anomaly_score=5.25,
                threshold=4.2,
                model_version="package-test-v1",
                model_lineage=create_model_lineage(
                    package_id="package-test-v1",
                    threshold=4.2,
                ),
                latency_ms=25,
            )

    was_processed = process_next_prediction(
        db,
        inference_service=DeterministicInferenceService(),
    )

    db.expire_all()
    completed_prediction = db.get(Prediction, prediction.id)

    assert was_processed is True
    assert completed_prediction is not None
    assert completed_prediction.status == PredictionStatus.COMPLETED.value
    assert completed_prediction.predicted_label == "anomalous"
    assert completed_prediction.anomaly_score == pytest.approx(5.25)
    assert completed_prediction.threshold == pytest.approx(4.2)
    assert completed_prediction.confidence is None
    assert completed_prediction.model_version == "package-test-v1"
    assert completed_prediction.model_lineage["dataset_category"] == "tile"
    assert completed_prediction.latency_ms == 25
    assert completed_prediction.processing_started_at is not None
    assert completed_prediction.processing_started_at.tzinfo is None
    assert completed_prediction.completed_at is not None
    assert completed_prediction.completed_at.tzinfo is None
    assert completed_prediction.error_message is None


@pytest.mark.w6_inference_gate
def test_worker_persists_failure(
    client: TestClient,
    db: Session,
    test_user: User,
):
    prediction = create_queued_prediction(db, test_user.id)
    prediction.predicted_label = PredictionLabel.ANOMALOUS.value
    prediction.anomaly_score = 99.0
    prediction.threshold = 1.0
    prediction.model_version = "stale-package-v1"
    prediction.model_lineage = create_model_lineage(
        package_id="stale-package-v1",
        threshold=1.0,
    ).model_dump(mode="json")
    prediction.latency_ms = 999
    prediction.error_message = "stale error"
    prediction.completed_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()

    class FailingInferenceService:
        def predict(self, image_path: str) -> AnomalyInferenceResult:
            raise RuntimeError("Simulated inference failure")

    was_processed = process_next_prediction(
        db,
        inference_service=FailingInferenceService(),
    )

    db.expire_all()
    failed_prediction = db.get(Prediction, prediction.id)

    assert was_processed is False
    assert failed_prediction is not None
    assert failed_prediction.status == PredictionStatus.FAILED.value
    assert failed_prediction.error_message == (
        "RuntimeError: Simulated inference failure"
    )
    assert failed_prediction.processing_started_at is not None
    assert failed_prediction.processing_started_at.tzinfo is None
    assert failed_prediction.completed_at is not None
    assert failed_prediction.completed_at.tzinfo is None
    assert failed_prediction.predicted_label is None
    assert failed_prediction.anomaly_score is None
    assert failed_prediction.threshold is None
    assert failed_prediction.model_version is None
    assert failed_prediction.model_lineage is None
    assert failed_prediction.latency_ms is None

    token = create_access_token(subject=test_user.id)
    response = client.get(
        f"/predictions/{prediction.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == PredictionStatus.FAILED.value
    assert response.json()["failure_code"] == (
        PredictionFailureCode.INFERENCE_FAILED.value
    )
    assert "error_message" not in response.json()
    assert "Simulated inference failure" not in response.text


def test_result_commit_failure_rolls_back_and_session_processes_next_job(
    db: Session,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = create_queued_prediction(db, test_user.id)
    second = create_queued_prediction(db, test_user.id)

    class DeterministicInferenceService:
        def predict(self, image_path: str) -> AnomalyInferenceResult:
            lineage = create_model_lineage(
                package_id="package-transaction-v1",
                threshold=2.0,
            )
            return AnomalyInferenceResult(
                predicted_label=PredictionLabel.NORMAL,
                anomaly_score=2.0,
                threshold=2.0,
                model_version=lineage.package_id,
                model_lineage=lineage,
                latency_ms=3,
            )

    real_commit = db.commit
    commit_calls = 0

    def fail_result_commit_once() -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:
            raise SQLAlchemyError("simulated result commit failure")
        real_commit()

    monkeypatch.setattr(db, "commit", fail_result_commit_once)
    first_processed = process_next_prediction(
        db,
        inference_service=DeterministicInferenceService(),
    )
    monkeypatch.setattr(db, "commit", real_commit)

    assert first_processed is False
    db.expire_all()
    failed = db.get(Prediction, first.id)
    assert failed is not None
    assert failed.status == PredictionStatus.FAILED.value
    assert failed.predicted_label is None
    assert failed.anomaly_score is None
    assert failed.model_lineage is None
    assert failed.processing_started_at is not None
    assert failed.completed_at is not None
    assert failed.error_message is not None
    assert failed.error_message.startswith("SQLAlchemyError:")

    second_processed = process_next_prediction(
        db,
        inference_service=DeterministicInferenceService(),
    )

    assert second_processed is True
    db.expire_all()
    completed = db.get(Prediction, second.id)
    assert completed is not None
    assert completed.status == PredictionStatus.COMPLETED.value
    assert completed.anomaly_score == pytest.approx(2.0)
    assert completed.processing_started_at is not None


def test_worker_returns_false_when_queue_is_empty(db: Session):
    was_processed = process_next_prediction(db)

    assert was_processed is False


def test_worker_rejects_non_positive_poll_interval() -> None:
    with pytest.raises(ValueError, match="poll interval must be positive"):
        run_forever(0)


def create_image_bytes(
    image_format: str = "JPEG",
    size: tuple[int, int] = (16, 16),
) -> bytes:
    buffer = BytesIO()

    image = Image.new(
        mode="RGB",
        size=size,
        color=(120, 80, 40),
    )

    image.save(buffer, format=image_format)

    return buffer.getvalue()


def image_upload(
    content: bytes | None = None,
    filename: str = "test.jpg",
    content_type: str = "image/jpeg",
) -> dict:
    if content is None:
        content = create_image_bytes("JPEG")

    return {
        "image": (
            filename,
            BytesIO(content),
            content_type,
        )
    }


def create_test_inference_service(
    tmp_path: Path,
    *,
    threshold: float = 2.0,
) -> tuple[AnomalyInferenceService, ConstantFeatureExtractor]:
    fixture = write_package_fixture(tmp_path, threshold=threshold)
    extractor = ConstantFeatureExtractor(value=2.0)
    package = ModelPackageLoader(
        package_manifest_path=fixture.manifest_path,
        feature_bank_dir=fixture.feature_bank_dir,
        extractor_factory=lambda device: extractor,
    ).load()
    return AnomalyInferenceService(package=package), extractor


@pytest.mark.w6_inference_gate
def test_authenticated_upload_worker_and_readback_use_real_inference_path(
    client: TestClient,
    db: Session,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upload_directory = tmp_path / "uploads"
    monkeypatch.setattr(
        image_storage_service,
        "upload_directory",
        upload_directory,
    )
    inference_service, extractor = create_test_inference_service(
        tmp_path / "package",
        threshold=2.0,
    )

    queued_response = client.post(
        "/predictions",
        headers=auth_headers,
        files=image_upload(
            content=create_image_bytes("PNG"),
            filename="tile.png",
            content_type="image/png",
        ),
    )

    assert queued_response.status_code == 202
    prediction_id = queued_response.json()["prediction_id"]
    db.expire_all()
    queued = db.get(Prediction, prediction_id)
    assert queued is not None
    assert queued.user_id == test_user.id
    assert queued.status == PredictionStatus.QUEUED.value
    assert queued.processing_started_at is None
    assert queued.completed_at is None
    assert Path(queued.image_path).parent == upload_directory

    was_processed = process_next_prediction(
        db,
        inference_service=inference_service,
    )

    assert was_processed is True
    db.expire_all()
    completed = db.get(Prediction, prediction_id)
    assert completed is not None
    assert completed.status == PredictionStatus.COMPLETED.value
    assert completed.predicted_label == PredictionLabel.NORMAL.value
    assert completed.anomaly_score == pytest.approx(2.0)
    assert completed.threshold == pytest.approx(2.0)
    assert completed.model_version == inference_service.package.package_id
    assert completed.model_lineage["package_id"] == completed.model_version
    assert completed.model_lineage["schema_version"] == MODEL_PACKAGE_SCHEMA_VERSION
    assert completed.model_lineage["extractor_name"] == "torchvision.resnet18"
    assert completed.model_lineage["extractor_weights"] == "IMAGENET1K_V1"
    assert completed.model_lineage["feature_bank_sha256"].startswith("sha256:")
    assert completed.model_lineage["dataset_name"] == "MVTec AD"
    assert completed.model_lineage["dataset_category"] == "tile"
    assert completed.model_lineage["dataset_version"] == "dataset-v1"
    assert completed.model_lineage["manifest_fingerprint"].startswith("sha256:")
    assert completed.model_lineage["preprocessing_schema_version"] == (
        PREPROCESSING_SCHEMA_VERSION
    )
    assert completed.model_lineage["scorer_distance"] == "euclidean"
    assert completed.model_lineage["scorer_k"] == 1
    assert completed.latency_ms is not None
    assert completed.latency_ms >= 0
    assert completed.processing_started_at is not None
    assert completed.processing_started_at.tzinfo is None
    assert completed.completed_at is not None
    assert completed.completed_at.tzinfo is None
    assert completed.created_at.tzinfo is None
    assert completed.error_message is None
    assert extractor.received_images is not None
    assert extractor.received_images.shape == (1, 3, 224, 224)

    read_response = client.get(
        f"/predictions/{prediction_id}",
        headers=auth_headers,
    )

    assert read_response.status_code == 200
    result = read_response.json()
    assert result["status"] == PredictionStatus.COMPLETED.value
    assert result["predicted_label"] == PredictionLabel.NORMAL.value
    assert result["anomaly_score"] == pytest.approx(2.0)
    assert result["threshold"] == pytest.approx(2.0)
    assert result["model_version"] == completed.model_version
    assert result["model_lineage"] == completed.model_lineage
    assert result["latency_ms"] >= 0
    assert result["processing_started_at"] is not None
    assert result["completed_at"] is not None
    assert "image_path" not in result


@pytest.mark.w6_inference_gate
def test_completed_prediction_is_not_claimed_or_scored_twice(
    db: Session,
    test_user: User,
    tmp_path: Path,
) -> None:
    prediction = create_queued_prediction(db, test_user.id)
    image_path = tmp_path / "queued-image.png"
    image_path.write_bytes(create_image_bytes("PNG"))
    prediction.image_path = str(image_path)
    db.commit()
    inference_service, extractor = create_test_inference_service(tmp_path / "package")

    assert process_next_prediction(db, inference_service=inference_service) is True
    assert process_next_prediction(db, inference_service=inference_service) is False

    db.expire_all()
    completed = db.get(Prediction, prediction.id)
    assert completed is not None
    assert completed.status == PredictionStatus.COMPLETED.value
    assert extractor.extract_calls == 1


@pytest.mark.w6_inference_gate
def test_unavailable_production_package_becomes_safe_failed_result(
    client: TestClient,
    db: Session,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upload_directory = tmp_path / "uploads"
    monkeypatch.setattr(
        image_storage_service,
        "upload_directory",
        upload_directory,
    )
    monkeypatch.setattr(
        settings,
        "MODEL_PACKAGE_MANIFEST_PATH",
        str(tmp_path / "missing" / "run_manifest.json"),
    )
    monkeypatch.setattr(
        settings,
        "FEATURE_BANK_DIR",
        str(tmp_path / "missing" / "feature-bank"),
    )
    reset_anomaly_inference_service_cache_for_tests()
    reset_model_package_cache_for_tests()

    queued_response = client.post(
        "/predictions",
        headers=auth_headers,
        files=image_upload(),
    )
    prediction_id = queued_response.json()["prediction_id"]

    try:
        assert process_next_prediction(db) is False
    finally:
        reset_anomaly_inference_service_cache_for_tests()
        reset_model_package_cache_for_tests()

    db.expire_all()
    failed = db.get(Prediction, prediction_id)
    assert failed is not None
    assert failed.status == PredictionStatus.FAILED.value
    assert failed.error_message is not None
    assert failed.error_message.startswith("ModelPackageArtifactError:")
    assert failed.predicted_label is None
    assert failed.anomaly_score is None
    assert failed.threshold is None
    assert failed.model_version is None
    assert failed.model_lineage is None

    read_response = client.get(
        f"/predictions/{prediction_id}",
        headers=auth_headers,
    )
    assert read_response.status_code == 200
    public_result = read_response.json()
    assert public_result["status"] == PredictionStatus.FAILED.value
    assert public_result["failure_code"] == "inference_failed"
    assert "error_message" not in public_result
    assert "run_manifest.json" not in read_response.text


@pytest.mark.w6_inference_gate
def test_uploaded_image_preprocessing_failure_becomes_safe_failed_result(
    client: TestClient,
    db: Session,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upload_directory = tmp_path / "uploads"
    monkeypatch.setattr(
        image_storage_service,
        "upload_directory",
        upload_directory,
    )
    inference_service, _ = create_test_inference_service(tmp_path / "package")
    queued_response = client.post(
        "/predictions",
        headers=auth_headers,
        files=image_upload(),
    )
    prediction_id = queued_response.json()["prediction_id"]
    db.expire_all()
    queued = db.get(Prediction, prediction_id)
    assert queued is not None
    Path(queued.image_path).write_bytes(b"corrupt-after-storage")

    was_processed = process_next_prediction(
        db,
        inference_service=inference_service,
    )

    assert was_processed is False
    db.expire_all()
    failed = db.get(Prediction, prediction_id)
    assert failed is not None
    assert failed.status == PredictionStatus.FAILED.value
    assert failed.predicted_label is None
    assert failed.anomaly_score is None
    assert failed.threshold is None
    assert failed.model_version is None
    assert failed.model_lineage is None
    assert failed.latency_ms is None
    assert failed.processing_started_at is not None
    assert failed.processing_started_at.tzinfo is None
    assert failed.completed_at is not None
    assert failed.completed_at.tzinfo is None
    assert failed.error_message is not None
    assert failed.error_message.startswith("ImagePreprocessingError:")
    assert Path(failed.image_path).exists()

    read_response = client.get(
        f"/predictions/{prediction_id}",
        headers=auth_headers,
    )
    assert read_response.status_code == 200
    public_result = read_response.json()
    assert public_result["status"] == PredictionStatus.FAILED.value
    assert public_result["failure_code"] == "inference_failed"
    assert "error_message" not in public_result
    assert "corrupt-after-storage" not in read_response.text


def test_production_worker_does_not_import_placeholder_model_services() -> None:
    worker_source = Path(prediction_worker.__file__).read_text(encoding="utf-8")

    assert "mock_model_service" not in worker_source
    assert "model_service" not in worker_source


def test_create_prediction_rejects_unsupported_file_type(
    client: TestClient,
    auth_headers: dict[str, str],
):
    gif_contents = create_image_bytes("GIF")

    response = client.post(
        "/predictions",
        headers=auth_headers,
        files=image_upload(
            content=gif_contents,
            filename="image.gif",
            content_type="image/gif",
        ),
    )

    assert response.status_code == 415
    assert response.json()["detail"] == (
        "Only JPEG, PNG, and WebP images are supported."
    )


@pytest.mark.w6_inference_gate
def test_get_prediction_hides_other_users_prediction(
    client: TestClient,
    db: Session,
    test_user: User,
):
    other_user = User(
        email="other@example.com",
        hashed_password="not-a-real-password",
        full_name="Other User",
        is_active=True,
        is_admin=False,
    )

    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    prediction = create_queued_prediction(db, test_user.id)
    token = create_access_token(subject=other_user.id)

    response = client.get(
        f"/predictions/{prediction.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Prediction job not found."


def test_admin_can_read_another_users_prediction(
    client: TestClient,
    db: Session,
    test_user: User,
):
    admin = User(
        email="admin@example.com",
        hashed_password="not-a-real-password",
        full_name="Admin User",
        is_active=True,
        is_admin=True,
    )

    db.add(admin)
    db.commit()
    db.refresh(admin)

    prediction = create_queued_prediction(db, test_user.id)
    token = create_access_token(subject=admin.id)

    response = client.get(
        f"/predictions/{prediction.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == prediction.id


def test_create_prediction_rejects_empty_image(
    client: TestClient,
    auth_headers: dict[str, str],
):
    response = client.post(
        "/predictions",
        headers=auth_headers,
        files=image_upload(content=b""),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded image is empty."


def test_create_prediction_rejects_oversized_image(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "MAX_IMAGE_SIZE_MB", 1)

    oversized_content = b"x" * (1024 * 1024 + 1)

    response = client.post(
        "/predictions",
        headers=auth_headers,
        files=image_upload(content=oversized_content),
    )

    assert response.status_code == 413
    assert response.json()["detail"] == ("Image exceeds the maximum size of 1 MB.")


def test_create_prediction_rejects_invalid_token(
    client: TestClient,
):
    response = client.post(
        "/predictions",
        headers={
            "Authorization": "Bearer this-is-not-a-valid-jwt",
        },
        files=image_upload(),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Could not validate authentication credentials."
    )


def test_inactive_user_cannot_create_prediction(
    client: TestClient,
    db: Session,
):
    inactive_user = User(
        email="inactive@example.com",
        hashed_password="not-a-real-password",
        full_name="Inactive User",
        is_active=False,
        is_admin=False,
    )

    db.add(inactive_user)
    db.commit()
    db.refresh(inactive_user)

    token = create_access_token(subject=inactive_user.id)

    response = client.post(
        "/predictions",
        headers={"Authorization": f"Bearer {token}"},
        files=image_upload(),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "User account is inactive."


@pytest.mark.w6_inference_gate
def test_create_prediction_rejects_invalid_image_bytes(
    client: TestClient,
    auth_headers: dict[str, str],
):
    response = client.post(
        "/predictions",
        headers=auth_headers,
        files=image_upload(
            content=b"this-is-not-an-image",
            filename="fake.jpg",
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == ("The uploaded file is not a valid image.")


def test_create_prediction_rejects_mismatched_content_type(
    client: TestClient,
    auth_headers: dict[str, str],
):
    png_contents = create_image_bytes("PNG")

    response = client.post(
        "/predictions",
        headers=auth_headers,
        files=image_upload(
            content=png_contents,
            filename="image.jpg",
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 415
    assert response.json()["detail"] == (
        "The declared file type does not match the uploaded image."
    )


def test_create_prediction_accepts_png_image(
    client: TestClient,
    db: Session,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    with TemporaryDirectory(
        prefix="vddai-test-png-",
        dir=".",
    ) as temporary_directory:
        upload_directory = Path(temporary_directory)

        monkeypatch.setattr(
            image_storage_service,
            "upload_directory",
            upload_directory,
        )

        png_contents = create_image_bytes("PNG")

        response = client.post(
            "/predictions",
            headers=auth_headers,
            files=image_upload(
                content=png_contents,
                filename="test.png",
                content_type="image/png",
            ),
        )

        assert response.status_code == 202

        prediction_id = response.json()["prediction_id"]
        prediction = db.get(Prediction, prediction_id)

        assert prediction is not None
        assert prediction.image_path.endswith(".png")
        assert Path(prediction.image_path).exists()
