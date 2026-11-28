import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.api.request_logging import RequestLoggingMiddleware
from app.core.logging import (
    LogError,
    LogEvent,
    log_event,
    request_id_context,
    setup_logging,
)
from app.workers import prediction_worker


def read_structured_logs(
    capsys: pytest.CaptureFixture[str],
) -> tuple[str, list[dict[str, object]]]:
    captured = capsys.readouterr()
    raw_output = captured.out + captured.err
    events = [
        json.loads(line) for line in raw_output.splitlines() if line.startswith("{")
    ]
    return raw_output, events


def test_log_fields_are_bounded_and_use_utc(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logging.getLogger("vddai.lifecycle"), "disabled", True)
    setup_logging()
    marker = "private-route-token"
    token = request_id_context.set("not-a-trusted-request-id")
    try:
        log_event(
            LogEvent.READBACK,
            service="api",
            status=marker,
            latency_ms=-1,
            prediction_id=42,
            attempt=0,
            model_version=f"C:/private/{marker}",
            route=f"/predictions/42?token={marker}",
            method=marker,
        )
    finally:
        request_id_context.reset(token)

    raw, events = read_structured_logs(capsys)
    assert marker not in raw
    assert len(events) == 1
    record = events[0]
    assert record["schema_version"] == 1
    assert datetime.fromisoformat(record["timestamp"]).tzinfo == UTC
    assert record["prediction_id"] == record["job_id"] == 42
    assert record["attempt"] == 0
    for key in (
        "request_id",
        "status",
        "latency_ms",
        "model_version",
        "route",
        "method",
    ):
        assert record[key] is None


def test_api_setup_suppresses_access_paths_and_sanitizes_uvicorn_errors(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    access_logger = logging.getLogger("uvicorn.access")
    error_logger = logging.getLogger("uvicorn.error")
    monkeypatch.setattr(access_logger, "disabled", False)
    monkeypatch.setattr(error_logger, "disabled", False)
    monkeypatch.setattr(error_logger, "filters", error_logger.filters[:])
    access_logger.setLevel(logging.INFO)
    override = logging.StreamHandler()
    monkeypatch.setattr(access_logger, "handlers", [override])
    monkeypatch.setattr(error_logger, "handlers", [override])

    setup_logging(api=True)
    setup_logging(api=True)
    access_logger.info("GET /predictions?preview=private-access-query")
    try:
        raise ValueError("C:/private/private-exception-path")
    except ValueError:
        error_logger.exception("private-auth-header-or-payload")

    raw, events = read_structured_logs(capsys)
    assert "private-" not in raw
    assert "Traceback" not in raw
    assert [(event["event"], event["error_code"]) for event in events] == [
        (LogEvent.SERVER_ERROR, LogError.SERVER_ERROR)
    ]


def test_parallel_requests_get_distinct_ids_and_restore_context_on_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging()

    async def run_requests():
        started = []
        both_started = asyncio.Event()

        async def app(scope, receive, send):
            request_id = request_id_context.get()
            started.append(request_id)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), 2)
            assert request_id_context.get() == request_id
            if scope["path"] == "/error":
                raise RuntimeError("private-ASGI-error")
            await send({"type": "http.response.start", "status": 202, "headers": []})

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            pass

        wrapped = RequestLoggingMiddleware(app)

        async def invoke(path):
            previous = request_id_context.get()
            try:
                await wrapped(
                    {"type": "http", "method": "POST", "path": path}, receive, send
                )
            finally:
                assert request_id_context.get() == previous

        results = await asyncio.gather(
            invoke("/ok"), invoke("/error"), return_exceptions=True
        )
        assert results[0] is None and isinstance(results[1], RuntimeError)
        return started

    request_ids = asyncio.run(run_requests())
    raw, events = read_structured_logs(capsys)
    assert "private-ASGI-error" not in raw
    assert len(set(request_ids)) == 2
    assert all(re.fullmatch(r"[0-9a-f]{32}", item) for item in request_ids)
    assert {event["request_id"] for event in events} == set(request_ids)
    assert {event["http_status"] for event in events} == {202, None}
    error = next(event for event in events if event["status"] == "error")
    assert error["error_code"] == LogError.REQUEST_FAILED


def test_worker_entrypoint_keeps_fatal_failure_exit_and_hides_detail(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_interval):
        raise RuntimeError("private-worker-startup-connection-string")

    monkeypatch.setattr(prediction_worker, "run_forever", fail)
    with pytest.raises(SystemExit) as raised:
        prediction_worker.main()

    assert raised.value.code == 1
    raw, events = read_structured_logs(capsys)
    assert "private-worker-startup-connection-string" not in raw
    assert len(events) == 1
    assert events[0]["service"] == "worker"
    assert events[0]["event"] == LogEvent.WORKER_ERROR
    assert events[0]["status"] == "error"


@pytest.mark.parametrize(
    ("service", "module", "args"),
    [
        ("api", "uvicorn", ["app.main:app", "--host", "127.0.0.1", "--port", "0"]),
        ("worker", "app.workers.prediction_worker", []),
    ],
)
def test_service_startup_rejects_malformed_database_config_without_disclosure(
    service: str, module: str, args: list[str], tmp_path: Path
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    private_marker = f"private-{uuid4().hex}"
    environment = {
        **os.environ,
        "PYTHONPATH": str(project_root),
        "ENVIRONMENT": "test",
        "DATABASE_URL": (
            f"postgresql+psycopg://check:{private_marker}"
            f"@127.0.0.1:{private_marker}/disposable"
        ),
    }
    command = [sys.executable, "-B", "-m", module, *args]
    if sys.flags.isolated:
        # Embedded Python ignores PYTHONPATH. Run the same module as __main__
        # after putting the test's worktree on its import path.
        bootstrap = (
            "import runpy, sys; "
            "sys.path.insert(0, sys.argv.pop(1)); "
            "runpy.run_module(sys.argv.pop(1), run_name='__main__', alter_sys=True)"
        )
        command = [
            sys.executable,
            "-B",
            "-c",
            bootstrap,
            str(project_root),
            module,
            *args,
        ]

    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = (result.stdout + result.stderr).casefold()
    if any(
        private_value.casefold() in output
        for private_value in (
            private_marker,
            str(project_root),
            project_root.as_posix(),
            str(tmp_path),
            tmp_path.as_posix(),
            "Traceback",
        )
    ):
        pytest.fail("Service startup exposed private configuration or a traceback")
    assert result.returncode == 1
    (event,) = [
        json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")
    ]
    assert event["schema_version"] == 1
    assert event["service"] == service
    assert event["event"] == LogEvent.STARTUP_FAILED
    assert event["error_code"] == LogError.STARTUP_FAILED
    assert event["status"] == "error"
