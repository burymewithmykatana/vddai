from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.prediction import Prediction, PredictionStatus
from app.models.user import User
from app.services.anomaly_inference_service import AnomalyInferenceResult
from app.services.image_storage_service import image_storage_service
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
    prediction.model_lineage = {
        "schema_version": "vddai.inference_package.v1",
        "feature_bank_sha256": "sha256:abc",
    }
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
    assert response.json()["model_lineage"]["feature_bank_sha256"] == ("sha256:abc")


def test_worker_completes_queued_prediction(
    db: Session,
    test_user: User,
):
    prediction = create_queued_prediction(db, test_user.id)

    class DeterministicInferenceService:
        def predict(self, image_path: str) -> AnomalyInferenceResult:
            assert image_path == "uploads/test_image_001.jpg"
            return AnomalyInferenceResult(
                predicted_label="anomalous",
                anomaly_score=5.25,
                threshold=4.2,
                model_version="package-test-v1",
                model_lineage={
                    "schema_version": "vddai.inference_package.v1",
                    "dataset_category": "tile",
                },
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
    assert completed_prediction.model_lineage == {
        "schema_version": "vddai.inference_package.v1",
        "dataset_category": "tile",
    }
    assert completed_prediction.latency_ms == 25
    assert completed_prediction.completed_at is not None
    assert completed_prediction.error_message is None


def test_worker_persists_failure(
    db: Session,
    test_user: User,
):
    prediction = create_queued_prediction(db, test_user.id)

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
    assert failed_prediction.error_message == "Simulated inference failure"
    assert failed_prediction.completed_at is not None


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
