import os

import pytest

# These must be set before importing application modules because
# the SQLAlchemy engine is created during module import.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///./test_vddai.db"

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.prediction import Prediction, PredictionStatus
from app.models.user import User
from app.services.mock_model_service import mock_model_service
from app.workers.prediction_worker import process_next_prediction


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
        status=PredictionStatus.QUEUED.value,
        model_version="mock-v1",
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
    test_user: User,
):
    response = client.post(
        "/predictions",
        json={
            "user_id": test_user.id,
            "image_path": "uploads/test_image_001.jpg",
        },
    )

    assert response.status_code == 202

    data = response.json()

    assert data["prediction_id"] > 0
    assert data["status"] == PredictionStatus.QUEUED.value
    assert data["message"] == "Prediction job queued successfully."


def test_create_prediction_persists_job(
    client: TestClient,
    db: Session,
    test_user: User,
):
    response = client.post(
        "/predictions",
        json={
            "user_id": test_user.id,
            "image_path": "uploads/test_image_001.jpg",
        },
    )

    prediction_id = response.json()["prediction_id"]

    db.expire_all()
    prediction = db.get(Prediction, prediction_id)

    assert prediction is not None
    assert prediction.user_id == test_user.id
    assert prediction.image_path == "uploads/test_image_001.jpg"
    assert prediction.status == PredictionStatus.QUEUED.value


def test_create_prediction_for_missing_user(client: TestClient):
    response = client.post(
        "/predictions",
        json={
            "user_id": 9999,
            "image_path": "uploads/test_image_001.jpg",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


def test_create_prediction_validation_error(client: TestClient):
    response = client.post(
        "/predictions",
        json={
            "user_id": 1,
        },
    )

    assert response.status_code == 422


def test_get_prediction_job(
    client: TestClient,
    db: Session,
    test_user: User,
):
    prediction = create_queued_prediction(db, test_user.id)

    response = client.get(f"/predictions/{prediction.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == prediction.id
    assert data["user_id"] == test_user.id
    assert data["status"] == PredictionStatus.QUEUED.value
    assert data["predicted_label"] is None
    assert data["confidence"] is None


def test_get_missing_prediction_job(client: TestClient):
    response = client.get("/predictions/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Prediction job not found."


def test_worker_completes_queued_prediction(
    db: Session,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    prediction = create_queued_prediction(db, test_user.id)

    def deterministic_prediction(image_path: str) -> dict:
        assert image_path == "uploads/test_image_001.jpg"

        return {
            "predicted_label": "scratch",
            "confidence": 0.91,
            "model_version": "mock-test-v1",
            "latency_ms": 25,
        }

    monkeypatch.setattr(
        mock_model_service,
        "predict",
        deterministic_prediction,
    )

    was_processed = process_next_prediction(db)

    db.expire_all()
    completed_prediction = db.get(Prediction, prediction.id)

    assert was_processed is True
    assert completed_prediction is not None
    assert completed_prediction.status == PredictionStatus.COMPLETED.value
    assert completed_prediction.predicted_label == "scratch"
    assert completed_prediction.confidence == pytest.approx(0.91)
    assert completed_prediction.model_version == "mock-test-v1"
    assert completed_prediction.latency_ms == 25
    assert completed_prediction.completed_at is not None
    assert completed_prediction.error_message is None


def test_worker_persists_failure(
    db: Session,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    prediction = create_queued_prediction(db, test_user.id)

    def failing_prediction(image_path: str) -> dict:
        raise RuntimeError("Simulated inference failure")

    monkeypatch.setattr(
        mock_model_service,
        "predict",
        failing_prediction,
    )

    was_processed = process_next_prediction(db)

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