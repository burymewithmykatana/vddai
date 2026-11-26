"""W8D4 client scenarios; transport seams never stand in for live staging evidence."""

from contextlib import nullcontext
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
from unittest.mock import Mock, call

from jose import jwt
import pytest

from scripts import smoke_staging as smoke
from app.tests.test_inference_contract import base_prediction_payload, valid_lineage

ARGS = dict(
    base_url="https://staging.example.com",
    expected_fqdn="staging.example.com",
    expected_model_version="registry-v1",
    expected_package_id="package-v1",
    timeout_seconds=5,
    allow_staging_test_data=True,
)
PROBE_ACCOUNTS = {
    "origin": ARGS["base_url"],
    "owner": {
        "id": 2,
        "email": "owner@example.com",
        "password": "owner-test-password",
        "is_admin": False,
    },
    "other": {
        "id": 3,
        "email": "other@example.com",
        "password": "other-test-password",
        "is_admin": False,
    },
}


def probe_arguments(directory):
    accounts_file = directory / "accounts.json"
    accounts_file.write_text(json.dumps(PROBE_ACCOUNTS), encoding="utf-8")
    return {**ARGS, "accounts_file": str(accounts_file), "state_dir": str(directory)}


def completed():
    value = base_prediction_payload()
    value.update(
        status="completed",
        image_width=64,
        image_height=64,
        predicted_label="normal",
        anomaly_score=2.0,
        threshold=2.0,
        model_version="package-v1",
        model_lineage=valid_lineage(package_id="package-v1").model_dump(mode="json"),
        latency_ms=2,
        created_at="2026-08-31T01:00:00",
        processing_started_at="2026-08-31T01:00:01",
        completed_at="2026-08-31T01:00:02",
    )
    return value


class Scenario:
    def __init__(self, directory):
        self.args = probe_arguments(directory)
        self.pending = directory / smoke.PENDING_DIRECTORY
        self.calls = []
        self.result = completed()
        self.health_count = 0
        self.reads = 0
        self.environment = "staging"
        self.initial_model_version = ARGS["expected_model_version"]
        self.drift = False
        self.history_changed = False
        self.history_result = None
        self.second_changed = False
        self.second_result = None
        self.error_on_upload = False
        self.error_on_login = False
        self.wrong_subject = False
        self.leak_other_history = False
        self.preexisting_history = None
        self.competing_reservation = False
        self.cross_user_body = smoke.PREDICTION_NOT_FOUND
        self.missing_body = smoke.PREDICTION_NOT_FOUND
        self.queued_response = {"prediction_id": 1, "status": "queued"}
        self.terminal_failure = False
        self.never_finishes = False
        self.submitted = False
        self.clock = 0.0
        self.tokens = {
            role: jwt.encode({"sub": str(account["id"])}, "synthetic-signing-key")
            for role, account in PROBE_ACCOUNTS.items()
            if role in {"owner", "other"}
        }

    def request(self, method, path, status, **kwargs):
        self.calls.append((method, path, status))
        self.clock += 0.1
        if path == "/health":
            return {"status": "ok", "environment": self.environment}
        if path == "/health/db":
            return {"status": "ok", "database": "connected"}
        if path == "/health/model":
            self.health_count += 1
            return {
                "status": "selected",
                "model_version": (
                    "changed"
                    if self.drift and self.health_count > 1
                    else self.initial_model_version
                ),
                "package_id": "package-v1",
            }
        if path == "/auth/login":
            if self.error_on_login:
                raise smoke.StagingSmokeError("unexpected_http_status")
            credentials = json.loads(kwargs["body"])
            role = credentials["email"].split("@")[0]
            assert credentials["password"] == PROBE_ACCOUNTS[role]["password"]
            token = self.tokens["owner" if self.wrong_subject else role]
            return {"access_token": token, "token_type": "bearer"}
        token = kwargs.get("token")
        if path == "/predictions" and method == "POST":
            assert token == self.tokens["owner"]
            assert b"image/png" in kwargs["body"]
            assert (self.pending / "run.json").is_file()
            if self.error_on_upload:
                raise smoke.StagingSmokeError("transport_failed")
            self.submitted = True
            return self.queued_response
        if status == 401:
            assert token is None
            return {"detail": "Could not validate authentication credentials."}
        if status == 404:
            assert token == self.tokens["other"]
            if path == smoke.MISSING_PREDICTION_PATH:
                return self.missing_body
            return self.cross_user_body
        if path == "/predictions":
            if not self.submitted:
                if token == self.tokens["other"] and self.competing_reservation:
                    self.pending.mkdir()
                return [self.result] if token == self.preexisting_history else []
            if token == self.tokens["other"] and not self.leak_other_history:
                return []
            if self.history_result is not None:
                return deepcopy(self.history_result)
            item = deepcopy(self.result)
            if self.history_changed:
                item["latency_ms"] = 99
            return [item]
        assert token == self.tokens["owner"]
        self.reads += 1
        if self.never_finishes or self.terminal_failure:
            terminal = self.terminal_failure
            return {
                **base_prediction_payload(),
                "image_width": 64,
                "image_height": 64,
                "created_at": "2026-08-31T01:00:00",
                "processing_started_at": "2026-08-31T01:00:01" if terminal else None,
                "completed_at": "2026-08-31T01:00:02" if terminal else None,
                "failure_code": "inference_failed" if terminal else None,
                "status": "failed" if terminal else "queued",
            }
        item = deepcopy(self.result)
        if self.reads > 1:
            if self.second_result is not None:
                return deepcopy(self.second_result)
            if self.second_changed:
                item["latency_ms"] = 99
        return item


@pytest.fixture
def scenario(monkeypatch, tmp_path):
    scenario = Scenario(tmp_path)
    monkeypatch.setattr(
        smoke.SmokeClient,
        "request",
        lambda self, *args, **kwargs: scenario.request(*args, **kwargs),
    )
    return scenario


def test_complete_flow_checks_ownership_persistence_and_final_identity(scenario):
    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["verdict"] == "PASS"
    assert evidence["prediction_id"] == 1
    assert evidence["cleanup_status"] == "pending"
    assert re.fullmatch(r"sha256:[a-f0-9]{64}", evidence["result_sha256"])
    assert len(evidence["passed_stages"]) == 7
    assert ("GET", "/predictions/1", 404) in scenario.calls
    assert ("GET", "/predictions/0", 404) in scenario.calls
    assert scenario.reads == 2 and scenario.health_count == 2
    assert [path for method, path, _ in scenario.calls if method == "POST"] == [
        "/auth/login",
        "/auth/login",
        "/predictions",
    ]
    run = json.loads((scenario.pending / "run.json").read_text(encoding="utf-8"))
    prediction = json.loads(
        (scenario.pending / "prediction.json").read_text(encoding="utf-8")
    )
    assert (run["run_id"], run["owner_id"], run["other_id"]) == (
        evidence["run_id"],
        2,
        3,
    )
    assert prediction == {"prediction_id": 1}
    for private in (
        *scenario.tokens.values(),
        "owner-test-password",
        "feature_bank_path",
    ):
        assert private not in json.dumps([evidence, run, prediction])


@pytest.mark.parametrize(
    "url",
    [
        "http://staging.example.com",
        "https://user@staging.example.com",
        "https://staging.example.com/path",
        "https://staging.example.com?x=1",
        "https://staging.example.com:444",
        "https://other.example.com",
        " https://staging.example.com",
        "https://staging.example.com/#",
    ],
)
def test_bad_origin_never_sends_request(scenario, url):
    assert (
        smoke.smoke_staging(**{**scenario.args, "base_url": url})["error_code"]
        == "invalid_staging_origin"
    )
    assert not scenario.calls


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_timeout_must_be_positive_finite(scenario, value):
    assert (
        smoke.smoke_staging(**{**scenario.args, "timeout_seconds": value})["error_code"]
        == "invalid_timeout"
    )
    assert not scenario.calls


def test_acknowledgement_required_before_network(scenario):
    assert (
        smoke.smoke_staging(**{**scenario.args, "allow_staging_test_data": False})[
            "verdict"
        ]
        == "FAIL"
    )
    assert not scenario.calls


@pytest.mark.parametrize(
    "environment", ["production", "test", "development", "", "STAGING", " staging "]
)
def test_environment_rejection_precedes_any_post(scenario, environment):
    scenario.environment = environment
    assert (
        smoke.smoke_staging(**scenario.args)["error_code"] == "invalid_staging_health"
    )
    assert all(method == "GET" for method, _, _ in scenario.calls)


def test_initial_model_mismatch_precedes_login_and_upload(scenario):
    scenario.initial_model_version = "unexpected-version"
    assert (
        smoke.smoke_staging(**scenario.args)["error_code"] == "model_identity_mismatch"
    )
    assert all(method == "GET" for method, _, _ in scenario.calls)
    assert not scenario.pending.exists()


@pytest.mark.parametrize(
    "other_update",
    [{"id": 2}, {"is_admin": True}, {"email": "OWNER@example.com"}, {"id": True}],
)
def test_invalid_probe_account_settings_precede_network(scenario, other_update):
    accounts = deepcopy(PROBE_ACCOUNTS)
    accounts["other"].update(other_update)
    Path(scenario.args["accounts_file"]).write_text(
        json.dumps(accounts), encoding="utf-8"
    )
    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["error_code"] == "invalid_probe_accounts"
    assert evidence["cleanup_status"] == "not_required"
    assert not scenario.calls and not scenario.pending.exists()


def test_account_settings_are_bound_to_the_staging_origin(scenario):
    Path(scenario.args["accounts_file"]).write_text(
        json.dumps({**PROBE_ACCOUNTS, "origin": "https://different.example.com"}),
        encoding="utf-8",
    )
    assert (
        smoke.smoke_staging(**scenario.args)["error_code"] == "invalid_probe_accounts"
    )
    assert not scenario.calls


@pytest.mark.parametrize(
    "attribute,code",
    [
        ("error_on_login", "unexpected_http_status"),
        ("wrong_subject", "probe_account_identity_mismatch"),
    ],
)
def test_authentication_failure_cannot_submit(scenario, attribute, code):
    setattr(scenario, attribute, True)
    assert smoke.smoke_staging(**scenario.args)["error_code"] == code
    assert ("POST", "/predictions", 202) not in scenario.calls
    assert not scenario.pending.exists()


@pytest.mark.parametrize("role", ["owner", "other"])
def test_probe_accounts_must_have_empty_histories(scenario, role):
    scenario.preexisting_history = scenario.tokens[role]
    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["error_code"] == "probe_history_not_empty"
    assert ("POST", "/predictions", 202) not in scenario.calls
    assert not scenario.pending.exists()


@pytest.mark.parametrize(
    "attribute,value,code",
    [
        ("cross_user_body", {"detail": "Wrong owner"}, "prediction_not_found_mismatch"),
        ("missing_body", {"detail": "Not found"}, "prediction_not_found_mismatch"),
        ("leak_other_history", True, "cross_user_history_not_empty"),
        ("terminal_failure", True, "prediction_not_successful"),
    ],
)
def test_ownership_and_terminal_failure_report_safe_codes(
    scenario, attribute, value, code
):
    setattr(scenario, attribute, value)
    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["error_code"] == code
    assert evidence["prediction_id"] == 1 and evidence["cleanup_status"] == "pending"
    assert "Wrong owner" not in json.dumps(evidence)


@pytest.mark.parametrize(
    "field", ["feature_bank_sha256", "dataset_version", "threshold_value"]
)
def test_full_lineage_is_required(scenario, field):
    del scenario.result["model_lineage"][field]
    assert (
        smoke.smoke_staging(**scenario.args)["error_code"]
        == "invalid_prediction_contract"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("confidence", 0.5),
        ("anomaly_score", True),
        ("id", 8),
        ("user_id", 3),
        ("image_width", 32),
        ("predicted_label", "anomalous"),
        ("completed_at", "2026-08-31T00:00:00"),
    ],
)
def test_bad_result_is_rejected(scenario, field, value):
    scenario.result[field] = value
    assert smoke.smoke_staging(**scenario.args)["verdict"] == "FAIL"


@pytest.mark.parametrize("field", ["id", "anomaly_score", "scorer_k"])
def test_owner_history_requires_matching_json_types(scenario, field):
    scenario.result["anomaly_score"] = 1.0
    history = deepcopy(scenario.result)
    if field == "scorer_k":
        history["model_lineage"][field] = True
    else:
        history[field] = True
    assert history == scenario.result  # Python equality alone misses this type change.
    scenario.history_result = [history]
    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["stage"] == "persistence_readback"
    assert evidence["error_code"] == "persisted_result_changed"
    assert "persistence_readback" not in evidence["passed_stages"]


def test_fresh_read_requires_matching_json_types(scenario):
    scenario.second_result = deepcopy(scenario.result)
    scenario.second_result["model_lineage"]["scorer_k"] = True
    assert scenario.second_result == scenario.result
    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["stage"] == "persistence_readback"
    assert evidence["error_code"] == "persisted_result_changed"


@pytest.mark.parametrize(
    "attribute,code",
    [
        ("drift", "model_identity_mismatch"),
        ("history_changed", "persisted_result_changed"),
        ("second_changed", "persisted_result_changed"),
        ("error_on_upload", "transport_failed"),
    ],
)
def test_failure_paths_do_not_pass_or_retry_post(scenario, attribute, code):
    setattr(scenario, attribute, True)
    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["error_code"] == code
    assert evidence["cleanup_status"] == "pending"
    assert scenario.calls.count(("POST", "/predictions", 202)) == 1
    if attribute == "error_on_upload":
        assert evidence["prediction_id"] is None
        assert not (scenario.pending / "prediction.json").exists()
    call_count = len(scenario.calls)
    repeat = smoke.smoke_staging(**scenario.args)
    assert repeat["error_code"] == "unresolved_probe_run"
    assert repeat["cleanup_status"] == "previous_run_pending"
    assert len(scenario.calls) == call_count


def test_competing_reservation_between_preflight_and_upload_blocks_upload(scenario):
    scenario.competing_reservation = True
    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["error_code"] == "unresolved_probe_run"
    assert evidence["cleanup_status"] == "previous_run_pending"
    assert not (scenario.pending / "run.json").exists()
    assert ("POST", "/predictions", 202) not in scenario.calls


def test_pending_record_write_failure_prevents_upload(scenario, monkeypatch):
    monkeypatch.setattr(smoke.os, "fsync", Mock(side_effect=OSError("private path")))
    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["error_code"] == "pending_record_unavailable"
    assert evidence["cleanup_status"] == "pending"
    assert "private path" not in json.dumps(evidence)
    assert ("POST", "/predictions", 202) not in scenario.calls
    assert scenario.pending.is_dir()


def test_pending_records_are_published_in_durable_order(scenario, monkeypatch):
    events = []
    save_json = smoke._save_json
    request = scenario.request

    def save_record(handle, record):
        save_json(handle, record)
        events.append("sync_prediction" if "prediction_id" in record else "sync_run")

    def log_upload(method, path, status, **kwargs):
        if method == "POST" and path == "/predictions":
            events.append("upload")
        return request(method, path, status, **kwargs)

    monkeypatch.setattr(smoke, "_save_json", save_record)
    monkeypatch.setattr(scenario, "request", log_upload)
    if os.name == "nt":
        move = smoke._move_write_through

        def record_move(source, destination):
            move(source, destination)
            events.append(destination.name)

        monkeypatch.setattr(smoke, "_move_write_through", record_move)
        expected = [
            smoke.PENDING_DIRECTORY,
            "sync_run",
            "run.json",
            "upload",
            "sync_prediction",
            "prediction.json",
        ]
    else:
        sync = smoke._sync_directory

        def record_sync(directory):
            sync(directory)
            events.append(
                "sync_pending" if directory == scenario.pending else "sync_state"
            )

        monkeypatch.setattr(smoke, "_sync_directory", record_sync)
        expected = [
            "sync_run",
            "sync_pending",
            "sync_state",
            "upload",
            "sync_prediction",
            "sync_pending",
        ]
    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["verdict"] == "PASS"
    assert events == expected


def test_new_process_recovers_pending_reservation_and_prediction_id(scenario):
    original = smoke.smoke_staging(**scenario.args)
    assert original["verdict"] == "PASS"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; from scripts import smoke_staging as smoke; "
            "evidence = smoke._new_evidence(sys.argv[1]); "
            "smoke._restore_pending_evidence(evidence, sys.argv[2]); "
            "print(json.dumps(evidence))",
            original["run_id"],
            scenario.args["state_dir"],
        ],
        cwd=smoke.ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    recovered = json.loads(result.stdout)
    assert recovered["cleanup_status"] == "pending"
    assert recovered["prediction_id"] == original["prediction_id"] == 1
    assert smoke.smoke_staging(**scenario.args)["error_code"] == "unresolved_probe_run"
    assert scenario.calls.count(("POST", "/predictions", 202)) == 1


@pytest.mark.parametrize("checkpoint", ["reservation", "run", "prediction"])
def test_pending_metadata_durability_failure_fails_closed(
    scenario, monkeypatch, checkpoint
):
    if os.name == "nt":
        move = smoke._move_write_through
        failed_destination = {
            "reservation": smoke.PENDING_DIRECTORY,
            "run": "run.json",
            "prediction": "prediction.json",
        }[checkpoint]

        def fail_move(source, destination):
            if destination.name == failed_destination:
                raise OSError("private storage detail")
            move(source, destination)

        monkeypatch.setattr(smoke, "_move_write_through", fail_move)
    else:
        sync = smoke._sync_directory

        def fail_sync(directory):
            if directory == scenario.pending.parent:
                step = "reservation"
            else:
                step = (
                    "prediction" if (directory / "prediction.json").exists() else "run"
                )
            if step == checkpoint:
                raise OSError("private storage detail")
            sync(directory)

        monkeypatch.setattr(smoke, "_sync_directory", fail_sync)

    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["verdict"] == "FAIL"
    assert evidence["error_code"] == "pending_record_unavailable"
    assert "private storage detail" not in json.dumps(evidence)
    assert scenario.calls.count(("POST", "/predictions", 202)) == int(
        checkpoint == "prediction"
    )
    if checkpoint == "prediction":
        assert (
            evidence["prediction_id"] == 1 and evidence["cleanup_status"] == "pending"
        )
        assert (
            smoke.smoke_staging(**scenario.args)["error_code"] == "unresolved_probe_run"
        )


def test_invalid_queue_response_retains_known_prediction_id(scenario):
    scenario.queued_response["status"] = "invalid"
    evidence = smoke.smoke_staging(**scenario.args)
    assert evidence["error_code"] == "invalid_queue_response"
    assert evidence["prediction_id"] == 1
    assert json.loads((scenario.pending / "prediction.json").read_text()) == {
        "prediction_id": 1
    }


def test_queue_deadline_is_bounded(scenario, monkeypatch):
    scenario.never_finishes = True
    monkeypatch.setattr(smoke.time, "monotonic", lambda: scenario.clock)
    monkeypatch.setattr(
        smoke.time,
        "sleep",
        lambda seconds: setattr(scenario, "clock", scenario.clock + seconds),
    )
    assert smoke.smoke_staging(**scenario.args)["error_code"] == "deadline_exceeded"


@pytest.mark.parametrize(
    "status,body,code",
    [
        (302, b"secret", "redirect_refused"),
        (500, b"secret", "unexpected_http_status"),
        (200, b"NaN", "invalid_response"),
        (200, b"secret", "invalid_response"),
        (200, b"x" * (smoke.MAX_RESPONSE_BYTES + 1), "response_too_large"),
    ],
    ids=["redirect", "http-error", "nonfinite", "malformed", "oversized"],
)
def test_transport_fails_safely_without_following_redirects(
    monkeypatch, status, body, code
):
    connection = Mock()
    response = connection.getresponse.return_value
    response.status = status
    chunks = [body, b""]
    response.read1.side_effect = lambda count: chunks.pop(0)
    factory = Mock(return_value=connection)
    monkeypatch.setattr(smoke.http.client, "HTTPSConnection", factory)
    with pytest.raises(smoke.StagingSmokeError, match=code):
        smoke.SmokeClient(ARGS["base_url"], 5).request("POST", "/auth/login", 200)
    assert factory.call_count == 1
    connection.close.assert_called_once()


def test_tls_verification_cannot_be_disabled(monkeypatch):
    connection = Mock()
    connection.connect.side_effect = ssl.SSLCertVerificationError("private detail")
    factory = Mock(return_value=connection)
    monkeypatch.setattr(smoke.http.client, "HTTPSConnection", factory)
    with pytest.raises(smoke.StagingSmokeError, match="transport_failed"):
        smoke.SmokeClient(ARGS["base_url"], 5).request("GET", "/health", 200)
    context = factory.call_args.kwargs["context"]
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED


def test_direct_cli_runs_from_outside_repository(tmp_path):
    result = subprocess.run(
        [sys.executable, str(smoke.ROOT / "scripts/smoke_staging.py"), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--allow-staging-test-data" in result.stdout
    assert "--accounts-file" in result.stdout
    assert "--state-dir" in result.stdout


def set_cli_arguments(monkeypatch, args, output):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smoke_staging.py",
            "--base-url",
            args["base_url"],
            "--expected-fqdn",
            args["expected_fqdn"],
            "--expected-model-version",
            args["expected_model_version"],
            "--expected-package-id",
            args["expected_package_id"],
            "--accounts-file",
            args["accounts_file"],
            "--state-dir",
            args["state_dir"],
            "--evidence-file",
            str(output),
            "--allow-staging-test-data",
        ],
    )


def test_cli_rejects_repository_evidence_destination_before_network(
    scenario, monkeypatch, capsys
):
    output = smoke.ROOT / "do-not-create.json"
    set_cli_arguments(monkeypatch, scenario.args, output)
    assert smoke.main() == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "invalid_evidence_path"
    assert not output.exists() and not scenario.calls


def test_cli_reserves_evidence_before_any_network_and_never_overwrites(
    scenario, monkeypatch, capsys, tmp_path
):
    output = tmp_path / "prior.json"
    output.write_text("prior report", encoding="utf-8")
    set_cli_arguments(monkeypatch, scenario.args, output)
    supervisor = Mock()
    monkeypatch.setattr(smoke, "run_bounded", supervisor)
    assert smoke.main() == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "invalid_evidence_path"
    assert output.read_text(encoding="utf-8") == "prior report"
    supervisor.assert_not_called()


def test_cli_saves_reports_and_can_run_again_after_operator_reconciliation(
    scenario, monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(
        smoke, "run_bounded", lambda options: smoke.smoke_staging(**options)
    )
    first = tmp_path / "first.json"
    set_cli_arguments(monkeypatch, scenario.args, first)
    assert smoke.main() == 0
    evidence = json.loads(first.read_text(encoding="utf-8"))
    assert evidence == json.loads(capsys.readouterr().out)
    assert evidence["verdict"] == "PASS" and evidence["cleanup_status"] == "pending"

    blocked = tmp_path / "blocked.json"
    set_cli_arguments(monkeypatch, scenario.args, blocked)
    assert smoke.main() == 1
    assert (
        json.loads(blocked.read_text(encoding="utf-8"))["error_code"]
        == "unresolved_probe_run"
    )
    assert scenario.calls.count(("POST", "/predictions", 202)) == 1

    # Model operator archival and an empty history after the test row is cleared.
    scenario.pending.rename(tmp_path / "reconciled")
    scenario.submitted = False
    last = tmp_path / "last.json"
    set_cli_arguments(monkeypatch, scenario.args, last)
    assert smoke.main() == 0
    assert json.loads(last.read_text(encoding="utf-8"))["run_id"] != evidence["run_id"]
    assert scenario.calls.count(("POST", "/predictions", 202)) == 2


def test_cli_returns_failure_when_report_cannot_be_saved(
    scenario, monkeypatch, capsys, tmp_path
):
    output = tmp_path / "report.json"
    set_cli_arguments(monkeypatch, scenario.args, output)
    monkeypatch.setattr(smoke, "run_bounded", Mock(return_value={"verdict": "PASS"}))
    monkeypatch.setattr(smoke.os, "fsync", Mock(side_effect=OSError("private path")))
    assert smoke.main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "verdict": "FAIL",
        "error_code": "evidence_write_failed",
    }
    assert output.read_bytes() == b""
    assert not list(tmp_path.glob(".w8d4-*"))


def mock_worker(monkeypatch, communicate, returncode=0):
    worker = Mock(returncode=returncode)
    worker.communicate.side_effect = communicate
    start = Mock(return_value=nullcontext(worker))
    monkeypatch.setattr(smoke.subprocess, "Popen", start)
    return worker, start


def test_cli_supervisor_bounds_blocked_resolver_and_discards_partial_output(
    scenario,
    monkeypatch,
):
    worker, start = mock_worker(
        monkeypatch, subprocess.TimeoutExpired("worker", 5, output="secret-token")
    )
    evidence = smoke.run_bounded(scenario.args)
    assert evidence["error_code"] == "deadline_exceeded"
    assert evidence["verdict"] == "FAIL" and evidence["prediction_id"] is None
    assert evidence["cleanup_status"] == "not_required"
    assert "secret-token" not in json.dumps(evidence)
    assert worker.communicate.call_args.kwargs["timeout"] == 5
    assert worker.method_calls[-2:] == [call.kill(), call.wait()]
    start.assert_called_once()


@pytest.mark.parametrize("known_id", [1, None])
def test_cli_supervisor_recovers_pending_status_and_any_saved_id(
    scenario, monkeypatch, known_id
):
    scenario.error_on_upload = known_id is None

    def timeout_after_upload(*, input, timeout):
        options = json.loads(input)
        assert all(
            account["password"] not in input
            for account in (PROBE_ACCOUNTS["owner"], PROBE_ACCOUNTS["other"])
        )
        smoke.smoke_staging(**options)
        raise subprocess.TimeoutExpired("worker", timeout, output="private")

    worker, _ = mock_worker(monkeypatch, timeout_after_upload)
    evidence = smoke.run_bounded(scenario.args)
    assert worker.method_calls[-2:] == [call.kill(), call.wait()]
    assert evidence["error_code"] == "deadline_exceeded"
    assert evidence["cleanup_status"] == "pending"
    assert evidence["prediction_id"] == known_id
    assert evidence["expected_package_id"] == ARGS["expected_package_id"]
    assert "private" not in json.dumps(evidence)
    assert smoke.smoke_staging(**scenario.args)["error_code"] == "unresolved_probe_run"
    assert scenario.calls.count(("POST", "/predictions", 202)) == 1


@pytest.mark.parametrize(
    "point,known_id,cleanup_status",
    [
        ("before_reservation", None, "not_required"),
        ("ambiguous_upload", None, "pending"),
        ("known_prediction", 1, "pending"),
    ],
)
def test_cli_operator_interrupt_saves_safe_evidence(
    scenario, monkeypatch, capsys, tmp_path, point, known_id, cleanup_status
):
    output = tmp_path / "cancelled.json"
    set_cli_arguments(monkeypatch, scenario.args, output)
    scenario.error_on_upload = point == "ambiguous_upload"

    def interrupt(*, input, timeout):
        if point != "before_reservation":
            smoke.smoke_staging(**json.loads(input))
        raise KeyboardInterrupt("private interruption detail")

    worker, start = mock_worker(monkeypatch, interrupt)
    restore = smoke._restore_pending_evidence

    def restore_after_child_stops(evidence, state_dir):
        assert worker.method_calls[-2:] == [call.kill(), call.wait()]
        restore(evidence, state_dir)

    monkeypatch.setattr(smoke, "_restore_pending_evidence", restore_after_child_stops)
    assert smoke.main() == 1
    stdout, stderr = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence == json.loads(stdout)
    assert "private interruption detail" not in stdout and not stderr
    assert evidence["verdict"] == "FAIL"
    assert evidence["stage"] == "supervisor"
    assert evidence["error_code"] == "operator_interrupted"
    assert evidence["prediction_id"] == known_id
    assert evidence["cleanup_status"] == cleanup_status
    start.assert_called_once()
    if point == "before_reservation":
        assert not scenario.calls and not scenario.pending.exists()
    else:
        assert (
            smoke.smoke_staging(**scenario.args)["error_code"] == "unresolved_probe_run"
        )
        assert scenario.calls.count(("POST", "/predictions", 202)) == 1


def test_cli_supervisor_reaps_child_through_a_second_interrupt(scenario, monkeypatch):
    worker, _ = mock_worker(monkeypatch, KeyboardInterrupt())
    worker.wait.side_effect = [KeyboardInterrupt(), 1]
    evidence = smoke.run_bounded(scenario.args)
    assert worker.method_calls[-4:] == [
        call.kill(),
        call.wait(),
        call.kill(),
        call.wait(),
    ]
    assert evidence["error_code"] == "operator_interrupted"


def test_cli_interrupt_after_supervisor_handoff_recovers_known_prediction(
    scenario, monkeypatch, capsys, tmp_path
):
    output = tmp_path / "cancelled-handoff.json"
    set_cli_arguments(monkeypatch, scenario.args, output)

    def interrupt_handoff(options):
        smoke.smoke_staging(**options)
        raise KeyboardInterrupt()

    monkeypatch.setattr(smoke, "run_bounded", interrupt_handoff)
    assert smoke.main() == 1
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence == json.loads(capsys.readouterr().out)
    assert evidence["error_code"] == "operator_interrupted"
    assert evidence["stage"] == "supervisor"
    assert evidence["prediction_id"] == 1 and evidence["cleanup_status"] == "pending"
    assert scenario.calls.count(("POST", "/predictions", 202)) == 1


def test_cli_interrupt_during_report_write_retains_known_prediction(
    scenario, monkeypatch, capsys, tmp_path
):
    output = tmp_path / "cancelled-report.json"
    set_cli_arguments(monkeypatch, scenario.args, output)
    monkeypatch.setattr(
        smoke, "run_bounded", lambda options: smoke.smoke_staging(**options)
    )
    finish = smoke._finish_report
    attempts = Mock(side_effect=[KeyboardInterrupt(), None])

    def interrupt_first_save(path, evidence):
        attempts()
        finish(path, evidence)

    monkeypatch.setattr(smoke, "_finish_report", interrupt_first_save)
    assert smoke.main() == 1
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence == json.loads(capsys.readouterr().out)
    assert evidence["stage"] == "report"
    assert evidence["error_code"] == "operator_interrupted"
    assert evidence["verdict"] == "FAIL" and evidence["prediction_id"] == 1
    assert evidence["cleanup_status"] == "pending"
    assert scenario.calls.count(("POST", "/predictions", 202)) == 1


def test_cli_supervisor_discards_failed_worker_output(scenario, monkeypatch):
    _, start = mock_worker(monkeypatch, lambda **kwargs: ("private output", None), 1)
    assert smoke.run_bounded(scenario.args)["error_code"] == "smoke_process_failed"
    assert start.call_args.kwargs["stderr"] == subprocess.DEVNULL


def test_cli_supervisor_reads_preflight_failure_from_real_child(scenario):
    evidence = smoke.run_bounded(
        {
            **scenario.args,
            "base_url": "http://staging.example.com",
            "timeout_seconds": 60,
        }
    )
    assert evidence["stage"] == "preflight"
    assert evidence["error_code"] == "invalid_staging_origin"
    assert not scenario.pending.exists()
