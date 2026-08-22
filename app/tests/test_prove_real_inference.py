import subprocess
import sys
from pathlib import Path

import pytest

from scripts import prove_real_inference
from scripts.prove_real_inference import (
    InferenceGateError,
    validate_completed_prediction,
    validate_health_checks,
    validate_selected_package_evidence,
)

pytestmark = pytest.mark.w7_production_gate


def test_probe_supports_documented_direct_script_execution() -> None:
    repository_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [sys.executable, "scripts/prove_real_inference.py", "--help"],
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "real-inference flow" in result.stdout


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


def test_health_probe_accepts_safe_nonproduction_dependencies() -> None:
    assert (
        validate_health_checks(
            service={
                "status": "ok",
                "service": "vddai-backend",
                "environment": "development",
            },
            database={"status": "ok", "database": "connected"},
            model={
                "status": "selected",
                "model_version": "registry-v1",
                "package_id": "package-v1",
            },
        )
        == "development"
    )


@pytest.mark.parametrize(
    "unsafe_environment",
    [
        "production",
        "prod",
        "production-us",
        "staging",
        "",
        " development ",
        "unknown",
    ],
)
def test_health_probe_refuses_unsafe_environment(
    unsafe_environment: str,
) -> None:
    with pytest.raises(InferenceGateError, match="environment"):
        validate_health_checks(
            service={
                "status": "ok",
                "service": "vddai-backend",
                "environment": unsafe_environment,
            },
            database={"status": "ok", "database": "connected"},
            model={
                "status": "selected",
                "model_version": "registry-v1",
                "package_id": "package-v1",
            },
        )


def test_probe_refuses_unsafe_environment_before_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def health_request(*, url: str, **_kwargs: object) -> dict[str, object]:
        if url.endswith("/health/model"):
            return {
                "status": "selected",
                "model_version": "registry-v1",
                "package_id": "package-v1",
            }
        if url.endswith("/health/db"):
            return {"status": "ok", "database": "connected"}
        return {"status": "ok", "environment": "staging"}

    monkeypatch.setattr(prove_real_inference, "_request_json", health_request)
    monkeypatch.setattr(
        prove_real_inference,
        "_register_and_login",
        lambda *_args, **_kwargs: pytest.fail("registration must not run"),
    )

    with pytest.raises(InferenceGateError, match="disposable"):
        prove_real_inference.prove_real_inference(
            base_url="http://example.test",
            timeout_seconds=1,
        )


def test_health_probe_rejects_private_model_path() -> None:
    with pytest.raises(InferenceGateError, match="private field"):
        validate_health_checks(
            service={
                "status": "ok",
                "service": "vddai-backend",
                "environment": "test",
            },
            database={"status": "ok", "database": "connected"},
            model={
                "status": "selected",
                "model_version": "registry-v1",
                "package_id": "package-v1",
                "artifact_path": "C:/private/package",
            },
        )


@pytest.mark.parametrize(
    ("label", "score", "threshold"),
    [
        ("anomalous", 1.0, 2.0),
        ("normal", 3.0, 2.0),
    ],
)
def test_probe_rejects_decision_semantics_mismatch(
    label: str,
    score: float,
    threshold: float,
) -> None:
    payload = completed_prediction()
    payload.update(
        {
            "predicted_label": label,
            "anomaly_score": score,
            "threshold": threshold,
        }
    )

    with pytest.raises(InferenceGateError, match="score > threshold"):
        validate_completed_prediction(payload)


def test_probe_preserves_threshold_equality_as_normal() -> None:
    payload = completed_prediction()
    payload.update({"anomaly_score": 2.0, "threshold": 2.0})

    assert validate_completed_prediction(payload)["label"] == "normal"


@pytest.mark.parametrize(
    ("final_model", "result_package", "expected_message"),
    [
        (
            {"model_version": "registry-v2", "package_id": "package-v2"},
            "package-v1",
            "changed during",
        ),
        (
            {"model_version": "registry-v1", "package_id": "package-v1"},
            "package-v2",
            "does not match",
        ),
    ],
)
def test_probe_rejects_selection_drift_and_result_package_mismatch(
    final_model: dict[str, str],
    result_package: str,
    expected_message: str,
) -> None:
    initial_model = {
        "model_version": "registry-v1",
        "package_id": "package-v1",
    }

    with pytest.raises(InferenceGateError, match=expected_message):
        validate_selected_package_evidence(
            initial_model=initial_model,
            final_model=final_model,
            result={"package_id": result_package},
        )


def test_probe_accepts_stable_selected_package_evidence() -> None:
    selected_model = {
        "model_version": "registry-v1",
        "package_id": "package-v1",
    }

    validate_selected_package_evidence(
        initial_model=selected_model,
        final_model=selected_model,
        result={"package_id": "package-v1"},
    )
