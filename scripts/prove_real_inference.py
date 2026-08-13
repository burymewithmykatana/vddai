from __future__ import annotations

import argparse
import json
import math
import os
import time
import uuid
from io import BytesIO
from typing import Any
from urllib import error, request

from PIL import Image


class InferenceGateError(RuntimeError):
    """Raised when the deployed inference flow violates the W6D1 gate."""


def _json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _decode_json(body: bytes, *, context: str) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InferenceGateError(f"{context} returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise InferenceGateError(f"{context} returned a non-object JSON response.")
    return payload


def _request_json(
    *,
    method: str,
    url: str,
    expected_status: int,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    http_request = request.Request(
        url,
        data=body,
        headers=headers or {},
        method=method,
    )
    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            status = response.status
            response_body = response.read()
    except error.HTTPError as exc:
        status = exc.code
        response_body = exc.read()
    except error.URLError as exc:
        raise InferenceGateError(f"Unable to reach {url}: {exc.reason}") from exc

    if status != expected_status:
        detail = _decode_json(response_body, context=url).get("detail")
        raise InferenceGateError(
            f"{method} {url} returned {status}; expected {expected_status}. "
            f"Public detail: {detail!r}."
        )
    return _decode_json(response_body, context=url)


def _create_probe_image() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 64), color=(120, 80, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def _multipart_image_body(image_bytes: bytes) -> tuple[bytes, str]:
    boundary = f"vddai-w6-{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="image"; filename="w6-gate.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("ascii")
    body += image_bytes
    body += f"\r\n--{boundary}--\r\n".encode("ascii")
    return body, f"multipart/form-data; boundary={boundary}"


def _register_and_login(base_url: str, *, role: str) -> str:
    run_id = uuid.uuid4().hex
    email = f"w6-{role}-{run_id}@example.com"
    password = f"W6-{run_id}!"
    common_headers = {"Content-Type": "application/json"}
    _request_json(
        method="POST",
        url=f"{base_url}/auth/register",
        expected_status=201,
        body=_json_bytes(
            {
                "email": email,
                "password": password,
                "full_name": f"W6D1 {role.title()} Probe",
            }
        ),
        headers=common_headers,
    )
    login = _request_json(
        method="POST",
        url=f"{base_url}/auth/login",
        expected_status=200,
        body=_json_bytes({"email": email, "password": password}),
        headers=common_headers,
    )
    access_token = login.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise InferenceGateError("Login response did not include an access token.")
    return access_token


def validate_completed_prediction(payload: dict[str, Any]) -> dict[str, object]:
    if payload.get("status") != "completed":
        raise InferenceGateError("Prediction did not reach the completed state.")
    if payload.get("predicted_label") not in {"normal", "anomalous"}:
        raise InferenceGateError("Completed prediction has an invalid label.")

    for field in ("anomaly_score", "threshold"):
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InferenceGateError(f"Completed prediction has no numeric {field}.")
        if not math.isfinite(float(value)):
            raise InferenceGateError(f"Completed prediction has non-finite {field}.")

    latency_ms = payload.get("latency_ms")
    if isinstance(latency_ms, bool) or not isinstance(latency_ms, int):
        raise InferenceGateError("Completed prediction has invalid latency_ms.")
    if latency_ms < 0:
        raise InferenceGateError("Completed prediction has negative latency_ms.")

    model_version = payload.get("model_version")
    lineage = payload.get("model_lineage")
    if not isinstance(model_version, str) or not model_version:
        raise InferenceGateError("Completed prediction has no model version.")
    if not isinstance(lineage, dict) or lineage.get("package_id") != model_version:
        raise InferenceGateError(
            "Persisted model lineage does not match the package ID."
        )
    if payload.get("confidence") is not None:
        raise InferenceGateError("Deprecated confidence field must remain null.")
    if payload.get("failure_code") is not None:
        raise InferenceGateError("Completed prediction must not expose a failure code.")
    for private_field in ("image_path", "error_message"):
        if private_field in payload:
            raise InferenceGateError(
                f"Public prediction response exposed private field {private_field}."
            )

    return {
        "prediction_id": payload.get("id"),
        "label": payload["predicted_label"],
        "anomaly_score": payload["anomaly_score"],
        "threshold": payload["threshold"],
        "latency_ms": latency_ms,
        "package_id": model_version,
    }


def prove_real_inference(*, base_url: str, timeout_seconds: float) -> dict[str, object]:
    base_url = base_url.rstrip("/")
    owner_token = _register_and_login(base_url, role="owner")
    other_token = _register_and_login(base_url, role="other")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    upload_body, content_type = _multipart_image_body(_create_probe_image())
    queued = _request_json(
        method="POST",
        url=f"{base_url}/predictions",
        expected_status=202,
        body=upload_body,
        headers={**owner_headers, "Content-Type": content_type},
    )
    prediction_id = queued.get("prediction_id")
    if isinstance(prediction_id, bool) or not isinstance(prediction_id, int):
        raise InferenceGateError("Queue response did not include a prediction ID.")

    _request_json(
        method="GET",
        url=f"{base_url}/predictions/{prediction_id}",
        expected_status=404,
        headers=other_headers,
    )

    deadline = time.monotonic() + timeout_seconds
    while True:
        prediction = _request_json(
            method="GET",
            url=f"{base_url}/predictions/{prediction_id}",
            expected_status=200,
            headers=owner_headers,
        )
        status = prediction.get("status")
        if status == "completed":
            return validate_completed_prediction(prediction)
        if status == "failed":
            if prediction.get("failure_code") != "inference_failed":
                raise InferenceGateError(
                    "Failed prediction did not expose the stable public failure code."
                )
            if "error_message" in prediction or "image_path" in prediction:
                raise InferenceGateError(
                    "Failed response exposed internal diagnostics."
                )
            raise InferenceGateError(
                "The worker failed closed with inference_failed. Inspect worker logs "
                "for local artifact or package diagnostics."
            )
        if status not in {"queued", "processing"}:
            raise InferenceGateError(
                f"Prediction entered unexpected status {status!r}."
            )
        if time.monotonic() >= deadline:
            raise InferenceGateError(
                f"Prediction {prediction_id} did not finish within {timeout_seconds}s."
            )
        time.sleep(0.5)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prove the deployed W6D1 authenticated real-inference flow."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("W6_INFERENCE_BASE_URL", "http://api:8000"),
        help="Running VDDAI API base URL.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=120.0,
        help="Maximum time to wait for the worker's terminal result.",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    if arguments.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be positive.")
    try:
        summary = prove_real_inference(
            base_url=arguments.base_url,
            timeout_seconds=arguments.timeout_seconds,
        )
    except InferenceGateError as exc:
        raise SystemExit(f"W6D1 real-inference gate failed: {exc}") from exc
    print("W6D1 real-inference gate passed.")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
