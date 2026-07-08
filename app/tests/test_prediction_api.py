import os
from pathlib import Path

# Important:
# These environment variables must be set before importing app.main.
# Your app creates the SQLAlchemy engine from settings during import.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///./test_vddai.db"

MODEL_PATH = Path("artifacts/model.joblib")

if not MODEL_PATH.exists():
    from ml.train_baseline import train_baseline_model

    train_baseline_model()

from fastapi.testclient import TestClient

from app.main import app


def test_root_endpoint():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200

    data = response.json()

    assert data["message"] == "visual defect AI backend is running."
    assert data["docs"] == "/docs"


def test_health_check():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ok"
    assert data["service"] == "vddai-backend"
    assert data["environment"] == "test"


def test_predict_endpoint():
    payload = {
        "mean_radius": 14.2,
        "mean_texture": 20.5,
        "mean_perimeter": 90.2,
        "mean_area": 600.1,
        "mean_smoothness": 0.1,
    }

    with TestClient(app) as client:
        response = client.post("/predict", json=payload)

    assert response.status_code == 200

    data = response.json()

    assert "prediction" in data
    assert "prediction_label" in data

    assert data["prediction"] in [0, 1]
    assert data["prediction_label"] in ["benign", "malignant"]


def test_predict_endpoint_validation_error():
    payload = {
        "mean_radius": 14.2,
        "mean_texture": 20.5,
    }

    with TestClient(app) as client:
        response = client.post("/predict", json=payload)

    assert response.status_code == 422