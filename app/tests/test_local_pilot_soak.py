import json
import sys
import time
from contextlib import contextmanager
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from PIL import Image

from scripts import run_local_pilot_soak as soak


@pytest.fixture
def loopback_pilot():
    @contextmanager
    def start(handle):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                handle(self)

            do_POST = do_GET

            def log_message(self, *_):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
            thread.start()
            try:
                yield soak.LocalPilot(
                    server.server_port, "vddai-w9d5-fixture", "package-v1"
                )
            finally:
                server.shutdown()
                thread.join()

    return start


@pytest.fixture
def simulated_pilot(monkeypatch):
    now = 0.0

    def sleep(seconds):
        nonlocal now
        now += seconds

    clock = SimpleNamespace(monotonic=lambda: now, sleep=sleep)
    monkeypatch.setattr(soak, "time", clock)
    monkeypatch.setattr(soak, "synthetic_upload", lambda _: (b"image", "test/image"))
    pilot = soak.LocalPilot(8000, "vddai-w9d5-fixture", "package-v1")
    monkeypatch.setattr(pilot, "check_target", lambda: None)
    owners = iter(({"Authorization": "synthetic-a"}, {"Authorization": "synthetic-b"}))
    monkeypatch.setattr(pilot, "create_owner", lambda: next(owners))
    return pilot, clock


def completed(prediction_id):
    return {
        "id": prediction_id,
        "status": "completed",
        "predicted_label": "normal",
        "anomaly_score": 0.5,
        "threshold": 0.5,
        "latency_ms": 80,
        "model_version": "package-v1",
        "model_lineage": {"package_id": "package-v1"},
    }


def test_workload_profile_and_nearest_rank():
    assert [(phase.seconds, phase.jobs) for phase in soak.PHASES] == [
        (300, 10),
        (900, 60),
    ]
    assert soak.percentile95([]) is None
    assert soak.percentile95(list(range(1, 21))) == 19
    assert soak.percentile95([4]) == 4


@pytest.mark.parametrize("index", range(9))
def test_synthetic_upload_uses_supported_format_and_dimensions(index):
    body, content_type = soak.synthetic_upload(index)
    envelope = f"Content-Type: {content_type}\r\n\r\n".encode() + body
    message = BytesParser(policy=policy.default).parsebytes(envelope)
    (part,) = message.iter_parts()
    image = Image.open(BytesIO(part.get_payload(decode=True)))
    assert part.get_content_type() == f"image/{soak.FORMATS[index % 3].lower()}"
    assert image.format == soak.FORMATS[index % 3]
    assert image.size == soak.SIZES[index // 3]


@pytest.mark.parametrize(
    "port, service", [(80, "vddai-w9d5-fixture"), (8000, "vddai-live")]
)
def test_target_requires_loopback_port_scope_and_fixture_identity(port, service):
    with pytest.raises(soak.SoakError, match="invalid_disposable_target"):
        soak.LocalPilot(port, service, "package-v1")


def test_identity_guard_runs_before_account_creation(monkeypatch):
    pilot = soak.LocalPilot(8000, "vddai-w9d5-fixture", "package-v1")
    seen = []

    def request(method, path, expected, **_):
        seen.append((method, path))
        return {"status": "ok", "environment": "staging", "service": pilot.service}

    monkeypatch.setattr(pilot, "request", request)
    with pytest.raises(soak.SoakError, match="unexpected_local_service_identity"):
        soak.run_soak(pilot, {"phases": []})
    assert seen == [("GET", "/health")]


def test_client_does_not_follow_redirects(loopback_pilot):
    seen = []

    def respond(handler):
        seen.append((handler.command, handler.path))
        handler.send_response(307)
        handler.send_header("Location", "/redirected")
        handler.end_headers()

    with loopback_pilot(respond) as pilot:
        with pytest.raises(soak.SoakError, match="unexpected_http_status_307"):
            pilot.request("POST", "/predictions", 202, body=b"fixture")
    assert seen == [("POST", "/predictions")]


@pytest.mark.parametrize(("method", "stage"), [("POST", "headers"), ("GET", "body")])
def test_request_deadline_cancels_in_flight_exchange(loopback_pilot, method, stage):
    release = Event()
    started = Event()
    reads = []

    def respond(handler):
        started.set()
        if stage == "headers":
            release.wait(3)
            return
        handler.send_response(200)
        handler.send_header("Content-Length", "100")
        handler.end_headers()
        try:
            while not release.wait(0.04):
                handler.wfile.write(b" ")
                handler.wfile.flush()
                reads.append(1)
        except OSError:
            pass

    with loopback_pilot(respond) as pilot:
        start = time.monotonic()
        try:
            with pytest.raises(soak.SoakError, match="^job_deadline_exceeded$"):
                pilot.request(method, "/predictions", 200, deadline=start + 0.6)
            elapsed = time.monotonic() - start
        finally:
            release.set()
    assert started.is_set()
    assert 0.45 <= elapsed < 1.5
    if stage == "body":
        assert len(reads) > 1


def test_request_accepts_timely_json(loopback_pilot):
    def respond(handler):
        handler.send_response(200)
        handler.send_header("Content-Length", "11")
        handler.end_headers()
        handler.wfile.write(b'{"ok":true}')

    with loopback_pilot(respond) as pilot:
        assert pilot.request("GET", "/health", 200, deadline=time.monotonic() + 2) == {
            "ok": True
        }


def test_failed_terminal_result_halts_without_resubmission(
    monkeypatch, simulated_pilot
):
    pilot, _ = simulated_pilot
    calls = []

    def request(method, path, expected, **_):
        calls.append((method, path))
        if method == "POST":
            return {"prediction_id": 17, "status": "queued"}
        return {"status": "failed"}

    monkeypatch.setattr(pilot, "request", request)
    report = {"phases": []}
    with pytest.raises(soak.SoakError, match="non_successful_terminal_result"):
        soak.run_soak(pilot, report)
    assert calls == [("POST", "/predictions"), ("GET", "/predictions/17")]
    assert report["completed"] == 0
    assert report["phases"][0]["accepted"] == 1


@pytest.mark.parametrize("uploads", [(17, 17), (17, 18, 17)])
def test_recycled_queue_receipt_is_rejected_across_owners_and_phases(
    monkeypatch, simulated_pilot, uploads
):
    pilot, _ = simulated_pilot
    monkeypatch.setattr(
        soak, "PHASES", (soak.Phase("warmup", 4, 1), soak.Phase("steady", 4, 2))
    )
    issued = iter(uploads)
    reads = []

    def request(method, path, expected, **_):
        if method == "POST":
            return {"prediction_id": next(issued), "status": "queued"}
        reads.append(path)
        return completed(int(path.rsplit("/", 1)[-1]))

    monkeypatch.setattr(pilot, "request", request)
    report = {"phases": []}
    with pytest.raises(soak.SoakError, match="^duplicate_queue_receipt$"):
        soak.run_soak(pilot, report)
    assert reads == [f"/predictions/{prediction_id}" for prediction_id in uploads[:-1]]
    assert report["completed"] == len(uploads) - 1
    assert sum(phase["accepted"] for phase in report["phases"]) == len(uploads) - 1


def test_nonqueued_receipt_is_not_accepted(monkeypatch, simulated_pilot):
    pilot, _ = simulated_pilot

    def request(method, *_args, **_kwargs):
        assert method == "POST"
        return {"prediction_id": 17, "status": "completed"}

    monkeypatch.setattr(pilot, "request", request)
    report = {"phases": []}
    with pytest.raises(soak.SoakError, match="^invalid_queue_receipt$"):
        soak.run_soak(pilot, report)
    assert report["phases"][0]["accepted"] == 0


def test_distinct_jobs_complete_the_fixed_workload(monkeypatch, simulated_pilot):
    pilot, clock = simulated_pilot
    requests = []
    ids = iter(range(1, 71))

    def request(method, path, expected, *, deadline, headers, **_):
        requests.append((method, deadline, headers["Authorization"]))
        clock.sleep(0.02)
        if method == "POST":
            return {"prediction_id": next(ids), "status": "queued"}
        return completed(int(path.rsplit("/", 1)[-1]))

    monkeypatch.setattr(pilot, "request", request)
    report = {"phases": []}
    soak.run_soak(pilot, report)
    assert [phase["completed"] for phase in report["phases"]] == [10, 60]
    assert report["unexpected_failures"] == 0
    assert report["elapsed_seconds"] == 1200
    assert len(requests) == 140
    for post, read in zip(requests[::2], requests[1::2], strict=True):
        assert post[0] == "POST" and read[0] == "GET"
        assert post[1:] == read[1:]


def test_poll_sleep_stops_at_job_deadline(monkeypatch, simulated_pilot):
    pilot, clock = simulated_pilot
    calls = []

    def request(method, *_args, deadline, **_kwargs):
        calls.append(method)
        assert deadline == 15
        if method == "POST":
            clock.sleep(14.8)
            return {"prediction_id": 17, "status": "queued"}
        clock.sleep(0.05)
        return {"status": "processing"}

    monkeypatch.setattr(pilot, "request", request)
    report = {"phases": []}
    with pytest.raises(soak.SoakError, match="^job_deadline_exceeded$"):
        soak.run_soak(pilot, report)
    assert calls == ["POST", "GET"]
    assert report["elapsed_seconds"] == 15
    assert report["completed"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("predicted_label", ["private-payload"]),
        ("anomaly_score", 10**400),
        ("latency_ms", 10**400),
    ],
)
def test_malformed_terminal_result_has_sanitized_cli_receipt(
    monkeypatch, simulated_pilot, tmp_path, capsys, field, value
):
    pilot, _ = simulated_pilot
    destination = tmp_path / "report.json"

    def request(method, *_args, **_kwargs):
        if method == "POST":
            return {"prediction_id": 17, "status": "queued"}
        return {**completed(17), field: value}

    monkeypatch.setattr(pilot, "request", request)
    monkeypatch.setattr(soak, "LocalPilot", lambda *_: pilot)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "soak",
            "--port",
            "8000",
            "--expected-service",
            pilot.service,
            "--package-id",
            pilot.package,
            "--report",
            str(destination),
        ],
    )
    assert soak.main() == 1
    report = json.loads(destination.read_bytes())
    assert report["result"] == "failed"
    assert report["error"] == "invalid_terminal_result"
    assert report["completed"] == 0
    assert report["unexpected_failures"] == 1
    assert "private-payload" not in destination.read_text(encoding="utf-8")
    assert capsys.readouterr().err == ""
