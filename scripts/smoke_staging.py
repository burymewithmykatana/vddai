"""Explicit staging-only HTTPS smoke gate; never deploys or rolls back."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import http.client
import json
import math
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
import time
import uuid
from typing import Any, TextIO
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jose import JWTError, jwt
from pydantic import ValidationError
from app.schemas.prediction import PredictionRead
from scripts.prove_real_inference import (
    InferenceGateError,
    _create_probe_image,
    _multipart_image_body,
    validate_completed_prediction,
)

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_ACCOUNTS_BYTES = 16 * 1024
EVIDENCE_SCHEMA = "vddai.staging_smoke.v2"
PENDING_DIRECTORY = "w8d4-pending"
PREDICTION_NOT_FOUND = {"detail": "Prediction job not found."}
MISSING_PREDICTION_PATH = "/predictions/0"  # The API assigns positive IDs.
IDENTITY = re.compile(r"[a-z0-9][a-z0-9-]{0,199}\Z")
HOSTNAME = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]*\Z"
)


class StagingSmokeError(RuntimeError):
    """Stable codes only; never remote response text or credentials."""


def validate_staging_target(base_url: str, expected_fqdn: str) -> str:
    try:
        parsed = urlsplit(base_url)
        valid = (
            base_url == base_url.strip()
            and not any(ord(char) < 33 for char in base_url)
            and HOSTNAME.fullmatch(expected_fqdn) is not None
            and parsed.scheme == "https"
            and parsed.netloc in {expected_fqdn, expected_fqdn + ":443"}
            and parsed.hostname == expected_fqdn
            and parsed.port in {None, 443}
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and "?" not in base_url
            and "#" not in base_url
        )
    except ValueError:
        valid = False
    if not valid:
        raise StagingSmokeError("invalid_staging_origin")
    return "https://" + expected_fqdn


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON")


class SmokeClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.hostname = urlsplit(base_url).hostname
        self.deadline = time.monotonic() + timeout_seconds

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise StagingSmokeError("deadline_exceeded")
        return remaining

    def request(
        self,
        method: str,
        path: str,
        status: int,
        *,
        body: bytes | None = None,
        token: str | None = None,
        content_type: str = "application/json",
    ) -> Any:
        # No redirects, environment proxies, or retries (including ambiguous POST).
        connection = http.client.HTTPSConnection(
            self.hostname,
            timeout=min(10.0, self.remaining()),
            context=ssl.create_default_context(),
        )
        try:
            connection.connect()
            connection.sock.settimeout(min(10.0, self.remaining()))
            headers = {"Content-Type": content_type}
            if token is not None:
                headers["Authorization"] = "Bearer " + token
            connection.request(method, path, body=body, headers=headers)
            connection.sock.settimeout(min(10.0, self.remaining()))
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise StagingSmokeError("redirect_refused")
            if response.status != status:
                raise StagingSmokeError("unexpected_http_status")
            data = bytearray()
            while True:
                if connection.sock is not None:
                    connection.sock.settimeout(min(10.0, self.remaining()))
                chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - len(data)))
                self.remaining()
                data.extend(chunk)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise StagingSmokeError("response_too_large")
                if not chunk:
                    break
            return json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
        except (OSError, http.client.HTTPException) as exc:
            raise StagingSmokeError("transport_failed") from exc
        except (ValueError, UnicodeError) as exc:
            raise StagingSmokeError("invalid_response") from exc
        finally:
            connection.close()


def validate_staging_health(
    *,
    service: Any,
    database: Any,
    model: Any,
    expected_model_version: str,
    expected_package_id: str,
) -> None:
    if (
        not isinstance(service, dict)
        or service.get("environment") != "staging"
        or service.get("status") != "ok"
    ):
        raise StagingSmokeError("invalid_staging_health")
    if database != {"status": "ok", "database": "connected"}:
        raise StagingSmokeError("invalid_database_health")
    if model != {
        "status": "selected",
        "model_version": expected_model_version,
        "package_id": expected_package_id,
    }:
        raise StagingSmokeError("model_identity_mismatch")


def _external_path(value: str | Path, error_code: str) -> Path:
    try:
        supplied = Path(value)
        path = supplied.resolve()
        if (
            supplied.is_absolute()
            and not supplied.is_relative_to(ROOT)
            and not path.is_relative_to(ROOT)
        ):
            return path
    except (OSError, RuntimeError, ValueError):
        pass
    raise StagingSmokeError(error_code)


def _load_accounts(path: str, target: str) -> tuple[dict[str, Any], dict[str, Any]]:
    accounts_path = _external_path(path, "invalid_accounts_file")
    try:
        if not accounts_path.is_file():
            raise ValueError("not a file")
        with accounts_path.open("rb") as handle:
            content = handle.read(MAX_ACCOUNTS_BYTES + 1)
        if len(content) > MAX_ACCOUNTS_BYTES:
            raise ValueError("account settings too large")
        settings = json.loads(content.decode("utf-8"))
        if settings["origin"] != target:
            raise ValueError("wrong origin")
        owner, other = settings["owner"], settings["other"]
        for account in (owner, other):
            # The operator verifies these roles. The login API exposes only a JWT.
            if (
                type(account["id"]) is not int
                or account["id"] <= 0
                or account["is_admin"] is not False
                or not all(
                    isinstance(account[key], str) and account[key].strip()
                    for key in ("email", "password")
                )
            ):
                raise ValueError("invalid account")
        if owner["id"] == other["id"] or (
            owner["email"].casefold() == other["email"].casefold()
        ):
            raise ValueError("accounts must be distinct")
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise StagingSmokeError("invalid_probe_accounts") from None
    return owner, other


def _login(client: SmokeClient, account: dict[str, Any]) -> str:
    credentials = {
        "email": account["email"],
        "password": account["password"],
    }
    login = client.request(
        "POST", "/auth/login", 200, body=json.dumps(credentials).encode()
    )
    if not isinstance(login, dict) or login.get("token_type") != "bearer":
        raise StagingSmokeError("invalid_login")
    token = login.get("access_token")
    if not isinstance(token, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token
    ):
        raise StagingSmokeError("invalid_login")
    try:
        claims = jwt.get_unverified_claims(token)
    except JWTError:
        raise StagingSmokeError("invalid_login") from None
    # Compare the subject returned over verified TLS to the operator's ID.
    # The authenticated API requests still validate the token server-side.
    if claims.get("sub") != str(account["id"]):
        raise StagingSmokeError("probe_account_identity_mismatch")
    return token


def _move_write_through(source: Path, destination: Path) -> None:
    import ctypes
    from ctypes import wintypes

    move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
    move.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    move.restype = wintypes.BOOL
    movefile_write_through = 0x8
    if not move(str(source), str(destination), movefile_write_through):
        raise ctypes.WinError(ctypes.get_last_error())


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reserve_pending(path: Path) -> None:
    if os.name == "nt":
        # Publish a directory beside the destination with a write-through move.
        with TemporaryDirectory(dir=path.parent, prefix=".w8d4-") as staging:
            _move_write_through(Path(staging), path)
    else:
        path.mkdir(mode=0o700)


def _write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    if os.name == "nt":
        with TemporaryDirectory(dir=path.parent, prefix=".w8d4-") as staging:
            staged = Path(staging) / path.name
            with staged.open("x", encoding="utf-8") as handle:
                _save_json(handle, evidence)
            _move_write_through(staged, path)
        return
    with path.open("x", encoding="utf-8") as handle:
        _save_json(handle, evidence)
    _sync_directory(path.parent)


def _save_json(handle: TextIO, value: dict[str, Any]) -> None:
    json.dump(value, handle, indent=2, allow_nan=False)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())


def _new_evidence(run_id: str) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_SCHEMA,
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
        "verdict": "FAIL",
        "stage": "preflight",
        "passed_stages": [],
        "prediction_id": None,
        "cleanup_status": "not_required",
    }


def _prediction(payload: Any, prediction_id: int, owner_id: int) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != set(
        PredictionRead.model_fields
    ):
        raise StagingSmokeError("invalid_prediction_fields")
    if (
        type(payload.get("id")) is not int
        or payload["id"] != prediction_id
        or type(payload.get("user_id")) is not int
        or payload["user_id"] != owner_id
        or payload.get("confidence") is not None
    ):
        raise StagingSmokeError("invalid_prediction_identity")
    if (
        payload.get("image_format") != "PNG"
        or type(payload.get("image_width")) is not int
        or type(payload.get("image_height")) is not int
        or (payload["image_width"], payload["image_height"]) != (64, 64)
    ):
        raise StagingSmokeError("invalid_prediction_image")
    try:
        PredictionRead.model_validate(payload)
        if payload["status"] == "completed":
            validate_completed_prediction(payload)
    except (ValidationError, ValueError, InferenceGateError):
        raise StagingSmokeError("invalid_prediction_contract") from None
    return payload


def smoke_staging(
    *,
    base_url: str,
    expected_fqdn: str,
    expected_model_version: str,
    expected_package_id: str,
    accounts_file: str,
    state_dir: str,
    timeout_seconds: float = 120,
    allow_staging_test_data: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    evidence = _new_evidence(run_id or uuid.uuid4().hex)
    try:
        target = validate_staging_target(base_url, expected_fqdn)
        if not allow_staging_test_data:
            raise StagingSmokeError("test_data_acknowledgement_required")
        if not all(
            isinstance(value, str) and IDENTITY.fullmatch(value)
            for value in (expected_model_version, expected_package_id)
        ):
            raise StagingSmokeError("invalid_expected_identity")
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise StagingSmokeError("invalid_timeout")
        evidence.update(
            target=target,
            expected_model_version=expected_model_version,
            expected_package_id=expected_package_id,
        )
        directory = _external_path(state_dir, "invalid_state_directory")
        if not directory.is_dir():
            raise StagingSmokeError("invalid_state_directory")
        pending = directory / PENDING_DIRECTORY
        if os.path.lexists(pending):
            evidence["cleanup_status"] = "previous_run_pending"
            raise StagingSmokeError("unresolved_probe_run")
        owner, other = _load_accounts(accounts_file, target)
        owner_id = owner["id"]
        client = SmokeClient(target, timeout_seconds)

        def stage(name: str) -> None:
            evidence["stage"] = name

        def passed(name: str) -> None:
            evidence["passed_stages"].append(name)

        def health() -> None:
            validate_staging_health(
                service=client.request("GET", "/health", 200),
                database=client.request("GET", "/health/db", 200),
                model=client.request("GET", "/health/model", 200),
                expected_model_version=expected_model_version,
                expected_package_id=expected_package_id,
            )

        stage("health")
        health()
        passed("health")
        stage("authentication")
        client.request("GET", "/predictions", 401)
        owner_token = _login(client, owner)
        other_token = _login(client, other)
        for token in (owner_token, other_token):
            if client.request("GET", "/predictions", 200, token=token) != []:
                raise StagingSmokeError("probe_history_not_empty")
        passed("authentication")
        stage("upload_queue")
        body, media_type = _multipart_image_body(_create_probe_image())
        try:
            _reserve_pending(pending)
        except FileExistsError:
            evidence["cleanup_status"] = "previous_run_pending"
            raise StagingSmokeError("unresolved_probe_run") from None
        except OSError:
            raise StagingSmokeError("pending_record_unavailable") from None
        evidence["cleanup_status"] = "pending"
        try:
            _write_evidence(
                pending / "run.json",
                {
                    "run_id": evidence["run_id"],
                    "target": target,
                    "expected_model_version": expected_model_version,
                    "expected_package_id": expected_package_id,
                    "started_at": evidence["started_at"],
                    "owner_id": owner_id,
                    "other_id": other["id"],
                },
            )
            if os.name != "nt":
                # Persist the reservation name in its parent before uploading.
                _sync_directory(directory)
        except OSError:
            raise StagingSmokeError("pending_record_unavailable") from None
        queued = client.request(
            "POST",
            "/predictions",
            202,
            body=body,
            token=owner_token,
            content_type=media_type,
        )
        prediction_id = (
            queued.get("prediction_id") if isinstance(queued, dict) else None
        )
        if type(prediction_id) is not int or prediction_id <= 0:
            raise StagingSmokeError("invalid_queue_response")
        evidence["prediction_id"] = prediction_id
        try:
            _write_evidence(
                pending / "prediction.json", {"prediction_id": prediction_id}
            )
        except OSError:
            raise StagingSmokeError("pending_record_unavailable") from None
        if queued.get("status") != "queued":
            raise StagingSmokeError("invalid_queue_response")
        passed("upload_queue")
        stage("ownership")
        hidden = client.request(
            "GET", f"/predictions/{prediction_id}", 404, token=other_token
        )
        missing = client.request("GET", MISSING_PREDICTION_PATH, 404, token=other_token)
        if hidden != missing or hidden != PREDICTION_NOT_FOUND:
            raise StagingSmokeError("prediction_not_found_mismatch")
        if client.request("GET", "/predictions", 200, token=other_token) != []:
            raise StagingSmokeError("cross_user_history_not_empty")
        passed("ownership")
        stage("inference")
        while True:
            payload = _prediction(
                client.request(
                    "GET", f"/predictions/{prediction_id}", 200, token=owner_token
                ),
                prediction_id,
                owner_id,
            )
            if payload["status"] == "completed":
                if payload["model_version"] != expected_package_id:
                    raise StagingSmokeError("result_package_mismatch")
                break
            if payload["status"] not in {"queued", "processing"}:
                raise StagingSmokeError("prediction_not_successful")
            time.sleep(min(0.5, client.remaining()))
        passed("inference")
        stage("persistence_readback")
        second = _prediction(
            client.request(
                "GET", f"/predictions/{prediction_id}", 200, token=owner_token
            ),
            prediction_id,
            owner_id,
        )
        history = client.request("GET", "/predictions", 200, token=owner_token)
        if not isinstance(history, list) or len(history) != 1:
            raise StagingSmokeError("persisted_result_changed")
        try:
            stored = _prediction(history[0], prediction_id, owner_id)
            serialized, fresh, historical = (
                json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False)
                for item in (payload, second, stored)
            )
        except (StagingSmokeError, ValueError):
            raise StagingSmokeError("persisted_result_changed") from None
        if serialized != fresh or serialized != historical:
            raise StagingSmokeError("persisted_result_changed")
        evidence["result_sha256"] = "sha256:" + sha256(serialized.encode()).hexdigest()
        passed("persistence_readback")
        stage("final_health")
        health()
        client.remaining()
        passed("final_health")
        evidence.update(
            verdict="PASS",
            observed_model_version=expected_model_version,
            observed_package_id=expected_package_id,
        )
    except StagingSmokeError as exc:
        evidence["error_code"] = str(exc)
    evidence["finished_at"] = datetime.now(UTC).isoformat()
    return evidence


def run_bounded(options: dict[str, Any]) -> dict[str, Any]:
    """Stop the child before recovering state after a timeout or cancellation.

    Recover any ID saved for this run before the child was stopped.
    """
    timeout = options["timeout_seconds"]
    evidence = _new_evidence(options.get("run_id") or uuid.uuid4().hex)
    worker_options = {**options, "run_id": evidence["run_id"]}
    try:
        if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            return smoke_staging(**worker_options)
        with subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import json,sys; from scripts.smoke_staging import smoke_staging; print(json.dumps(smoke_staging(**json.load(sys.stdin))))",
            ],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        ) as worker:
            try:
                stdout, _ = worker.communicate(
                    input=json.dumps(worker_options), timeout=timeout
                )
            except (KeyboardInterrupt, subprocess.TimeoutExpired, OSError, ValueError):
                while True:
                    try:
                        worker.kill()
                        worker.wait()
                        break
                    except KeyboardInterrupt:
                        continue
                raise
        if worker.returncode != 0:
            raise ValueError("worker failed")
        result_evidence = json.loads(stdout)
        if (
            not isinstance(result_evidence, dict)
            or result_evidence.get("run_id") != evidence["run_id"]
            or result_evidence.get("verdict") not in {"PASS", "FAIL"}
        ):
            raise ValueError("invalid worker evidence")
        return result_evidence
    except subprocess.TimeoutExpired:
        code = "deadline_exceeded"
    except KeyboardInterrupt:
        code = "operator_interrupted"
    except (OSError, ValueError):
        code = "smoke_process_failed"
    evidence.update(
        stage="overall_deadline" if code == "deadline_exceeded" else "supervisor",
        error_code=code,
        finished_at=datetime.now(UTC).isoformat(),
    )
    _restore_pending_evidence(evidence, options["state_dir"])
    return evidence


def _restore_pending_evidence(evidence: dict[str, Any], state_dir: str) -> None:
    try:
        pending = (
            _external_path(state_dir, "invalid_state_directory") / PENDING_DIRECTORY
        )
        if not os.path.lexists(pending):
            return
        record = json.loads((pending / "run.json").read_text(encoding="utf-8"))
        if record["run_id"] != evidence["run_id"]:
            evidence["cleanup_status"] = "previous_run_pending"
            return
        evidence.update(
            cleanup_status="pending",
            target=record["target"],
            expected_model_version=record["expected_model_version"],
            expected_package_id=record["expected_package_id"],
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        StagingSmokeError,
    ):
        evidence["cleanup_status"] = "unknown"
        return
    try:
        record = json.loads((pending / "prediction.json").read_text(encoding="utf-8"))
        prediction_id = record["prediction_id"]
        if type(prediction_id) is int and prediction_id > 0:
            evidence["prediction_id"] = prediction_id
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        pass  # The reservation still blocks uploads if the ID never reached disk.


def _finish_report(path: Path, evidence: dict[str, Any]) -> None:
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".w8d4-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            _save_json(handle, evidence)
        temporary.replace(path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # The receipt remains uncommitted if replacement failed.


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default=os.environ.get("VDDAI_STAGING_BASE_URL", "")
    )
    parser.add_argument(
        "--expected-fqdn", default=os.environ.get("VDDAI_STAGING_FQDN", "")
    )
    parser.add_argument(
        "--expected-model-version",
        default=os.environ.get("VDDAI_EXPECTED_MODEL_VERSION", ""),
    )
    parser.add_argument(
        "--expected-package-id", default=os.environ.get("VDDAI_EXPECTED_PACKAGE_ID", "")
    )
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument(
        "--allow-staging-test-data",
        action="store_true",
        help="Authorize one synthetic prediction/image pending operator cleanup.",
    )
    parser.add_argument(
        "--accounts-file",
        required=True,
        help="Absolute path to the protected JSON settings for both staging accounts.",
    )
    parser.add_argument(
        "--state-dir",
        required=True,
        help="Fixed protected directory outside Git for this staging account pair.",
    )
    parser.add_argument(
        "--evidence-file",
        type=Path,
        required=True,
        help="Absolute path to a new JSON evidence file in the state directory.",
    )
    args = parser.parse_args()
    try:
        directory = _external_path(args.state_dir, "invalid_state_directory")
        if not directory.is_dir():
            raise StagingSmokeError("invalid_state_directory")
        output = _external_path(args.evidence_file, "invalid_evidence_path")
        if output.parent != directory or output.name == PENDING_DIRECTORY:
            raise StagingSmokeError("invalid_evidence_path")
        # Reserve the receipt before any remote calls. A fixed state directory
        # coordinates runs even when each invocation uses a different receipt.
        output.touch(exist_ok=False)
    except (OSError, StagingSmokeError) as exc:
        evidence = _new_evidence(uuid.uuid4().hex)
        evidence.update(
            error_code=(
                str(exc)
                if isinstance(exc, StagingSmokeError)
                else "invalid_evidence_path"
            ),
            finished_at=datetime.now(UTC).isoformat(),
        )
    else:
        evidence = _new_evidence(uuid.uuid4().hex)
        cancellation_stage = "supervisor"
        try:
            try:
                evidence = run_bounded(
                    dict(
                        base_url=args.base_url,
                        expected_fqdn=args.expected_fqdn,
                        expected_model_version=args.expected_model_version,
                        expected_package_id=args.expected_package_id,
                        accounts_file=args.accounts_file,
                        state_dir=str(directory),
                        timeout_seconds=args.timeout_seconds,
                        allow_staging_test_data=args.allow_staging_test_data,
                        run_id=evidence["run_id"],
                    )
                )
                cancellation_stage = "report"
                _finish_report(output, evidence)
            except KeyboardInterrupt:
                evidence.update(
                    verdict="FAIL",
                    stage=cancellation_stage,
                    error_code="operator_interrupted",
                    finished_at=datetime.now(UTC).isoformat(),
                )
                _restore_pending_evidence(evidence, str(directory))
                _finish_report(output, evidence)
        except OSError:
            evidence.update(verdict="FAIL", error_code="evidence_write_failed")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
