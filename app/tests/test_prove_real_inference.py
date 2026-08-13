import pytest

from scripts.prove_real_inference import (
    InferenceGateError,
    validate_completed_prediction,
)


def completed_prediction() -> dict[str, object]:
    return {
        "id": 42,
        "status": "completed",
        "predicted_label": "normal",
        "confidence": None,
        "anomaly_score": 1.25,
        "threshold": 2.0,
        "model_version": "package-v1",
        "model_lineage": {"package_id": "package-v1"},
        "latency_ms": 8,
        "failure_code": None,
    }


def test_completed_probe_result_returns_public_summary() -> None:
    assert validate_completed_prediction(completed_prediction()) == {
        "prediction_id": 42,
        "label": "normal",
        "anomaly_score": 1.25,
        "threshold": 2.0,
        "latency_ms": 8,
        "package_id": "package-v1",
    }


@pytest.mark.parametrize("private_field", ["image_path", "error_message"])
def test_probe_rejects_private_response_fields(private_field: str) -> None:
    payload = completed_prediction()
    payload[private_field] = "private detail"

    with pytest.raises(InferenceGateError, match="exposed private field"):
        validate_completed_prediction(payload)


def test_probe_rejects_package_lineage_mismatch() -> None:
    payload = completed_prediction()
    payload["model_lineage"] = {"package_id": "different-package"}

    with pytest.raises(InferenceGateError, match="lineage"):
        validate_completed_prediction(payload)
