import math
import socket
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.request import ProxyHandler, build_opener

import pytest
from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, settings
from app.db.base import Base
from app.main import app
from app.models.prediction import PredictionStatus
from app.services.image_storage_service import (
    ImageStorageError,
    StoredImageNotFoundError,
)
from app.services.metrics_service import (
    ApiMetrics,
    WorkerMetrics,
    _bind_address,
    serve_metrics,
    worker_metrics,
)
from app.tests.test_prediction_worker_reliability import (
    DeterministicInferenceService,
    MutableStorage,
    create_prediction,
    result_for,
)
from app.workers import prediction_worker
from app.workers.prediction_worker import PredictionRetryPolicy, process_next_prediction


@pytest.fixture
def metric_sessions() -> Iterator[sessionmaker]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


def test_queue_snapshot_counts_outstanding_states_and_ages(metric_sessions) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with metric_sessions() as db:
        create_prediction(db, created_at=now - timedelta(seconds=16))
        active = create_prediction(db, created_at=now - timedelta(seconds=12))
        active.start_processing(at=now, lease_expires_at=now + timedelta(seconds=30))
        waiting = create_prediction(db, created_at=now - timedelta(seconds=8))
        waiting.start_processing(at=now, lease_expires_at=now + timedelta(seconds=30))
        waiting.schedule_retry(
            expected_attempt=1,
            error_message="fixture",
            next_attempt_at=now + timedelta(seconds=5),
        )
        done = create_prediction(db, created_at=now - timedelta(seconds=25))
        done.start_processing(at=now, lease_expires_at=now + timedelta(seconds=30))
        done.complete(result_for("fixture-complete-v1"), expected_attempt=1, at=now)
        db.commit()

    registry = ApiMetrics(metric_sessions).registry
    assert registry.get_sample_value("vddai_database_ready") == 1
    for state, minimum_age in (("queued", 16), ("active", 12), ("retry_waiting", 8)):
        labels = {"state": state}
        assert registry.get_sample_value("vddai_queue_depth", labels) == 1
        assert (
            registry.get_sample_value("vddai_queue_oldest_age_seconds", labels)
            >= minimum_age
        )


def test_public_routes_and_private_metrics_listener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    def unavailable_database():
        raise SQLAlchemyError("private-database-detail")

    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_BIND_MODE", "loopback")
    monkeypatch.setattr(settings, "METRICS_API_PORT", port)
    monkeypatch.setattr("app.main.init_db", lambda: None)
    monkeypatch.setattr("app.main.SessionLocal", unavailable_database)

    with TestClient(app) as client:
        assert client.get("/health?token=private-query").status_code == 200
        assert client.get("/metrics").status_code == 404
        assert client.get("/private-unmatched-path").status_code == 404
        http = build_opener(ProxyHandler({}))
        with http.open(f"http://127.0.0.1:{port}/metrics", timeout=3) as response:
            text = response.read().decode("utf-8")
        assert "vddai_api_ready 1.0" in text
        assert "vddai_database_ready 0.0" in text
        assert "vddai_queue_depth" not in text
        assert (
            'vddai_http_requests_total{method="GET",route="/health",status_class="2xx"} 1.0'
            in text
        )
        assert (
            'vddai_http_requests_total{method="GET",route="unmatched",status_class="4xx"} 2.0'
            in text
        )
        assert "private-" not in text

    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)


def test_listener_opt_in_and_private_address(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_factory():
        pytest.fail("Disabled metrics initialized a collector.")

    with serve_metrics(
        Settings(METRICS_ENABLED=False), "worker", unexpected_factory
    ) as metrics:
        assert metrics is None

    monkeypatch.setattr("socket.gethostbyname", lambda _name: "0.0.0.0")
    with pytest.raises(ValueError, match="private"):
        _bind_address("container")
    monkeypatch.setattr("socket.gethostbyname", lambda _name: "172.20.0.5")
    assert _bind_address("container") == "172.20.0.5"


@pytest.mark.parametrize("service", ["api", "worker"])
def test_thread_start_failure_closes_listener_and_leaves_service_running(
    service: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    attempted = []

    class UnstartableThread:
        def __init__(self, *, target, daemon: bool):
            self.server = target.__self__

        def start(self):
            assert self.server.socket.getsockname() == ("127.0.0.1", port)
            attempted.append(True)
            raise RuntimeError("private-metrics-thread-detail")

    monkeypatch.setattr("app.services.metrics_service.Thread", UnstartableThread)
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_BIND_MODE", "loopback")
    monkeypatch.setattr(settings, "METRICS_API_PORT", port)
    monkeypatch.setattr(settings, "METRICS_WORKER_PORT", port)
    if service == "api":
        monkeypatch.setattr("app.main.init_db", lambda: None)
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert app.state.api_metrics is None
    else:
        polled = []

        def run_forever(_interval):
            assert worker_metrics.get() is None
            polled.append(True)

        monkeypatch.setattr(prediction_worker, "run_forever", run_forever)
        prediction_worker.main()
        assert polled == [True]

    output = capsys.readouterr()
    assert attempted == [True]
    assert "service.metrics_unavailable" in output.out
    assert "private-metrics-thread-detail" not in output.out + output.err
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)


def test_worker_metrics_follow_committed_retry_and_terminal_outcomes(
    metric_sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 8, 25, 10, 30)
    metrics = WorkerMetrics()
    registry = metrics.registry
    assert math.isnan(registry.get_sample_value("vddai_worker_model_ready"))
    monkeypatch.setattr(prediction_worker, "_utc_now_naive", lambda: now)
    storage = MutableStorage(error=ImageStorageError("private-fixture-path"))
    inference = DeterministicInferenceService(result_for("fixture-metrics-v1"))
    policy = PredictionRetryPolicy(3, 3, 15)
    token = worker_metrics.set(metrics)
    try:
        with metric_sessions() as db:
            job = create_prediction(db, created_at=now - timedelta(seconds=10))
            assert not process_next_prediction(db, inference, storage, policy)
            assert job.status == PredictionStatus.PROCESSING.value
            assert registry.get_sample_value("vddai_job_retries_scheduled_total") == 1
            assert (
                registry.get_sample_value(
                    "vddai_job_execution_failures_total", {"stage": "storage"}
                )
                == 1
            )
            assert (
                registry.get_sample_value(
                    "vddai_job_terminal_total", {"status": "failed"}
                )
                == 0
            )

            storage.error = None
            now += timedelta(seconds=3)
            assert process_next_prediction(db, inference, storage, policy)
            assert job.status == PredictionStatus.COMPLETED.value
            assert job.attempt_count == 2
            assert not process_next_prediction(db, inference, storage, policy)
    finally:
        worker_metrics.reset(token)

    for kind in ("initial", "retry"):
        assert registry.get_sample_value("vddai_job_claims_total", {"kind": kind}) == 1
    complete = {"status": "completed"}
    assert registry.get_sample_value("vddai_job_terminal_total", complete) == 1
    assert registry.get_sample_value("vddai_job_duration_seconds_sum", complete) == 13
    assert registry.get_sample_value("vddai_inference_duration_seconds_sum") == 0.004
    assert registry.get_sample_value("vddai_worker_model_ready") == 1
    assert registry.get_sample_value("vddai_worker_ready") == 1
    assert b"private-fixture-path" not in generate_latest(registry)


@pytest.mark.parametrize(
    ("outcome", "expected_status", "terminal_observed"),
    [
        ("success", PredictionStatus.COMPLETED.value, True),
        ("terminal_failure", PredictionStatus.FAILED.value, True),
        ("commit_rejected", PredictionStatus.PROCESSING.value, False),
        ("commit_unacknowledged", PredictionStatus.COMPLETED.value, False),
    ],
)
def test_job_duration_uses_successful_commit_and_excludes_ambiguous_results(
    metric_sessions,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    expected_status: str,
    terminal_observed: bool,
) -> None:
    settled_at = now = datetime(2026, 8, 25, 10, 30)
    monkeypatch.setattr(prediction_worker, "_utc_now_naive", lambda: now)
    metrics = WorkerMetrics()
    successful_inference = DeterministicInferenceService(
        result_for("fixture-metrics-v1")
    )
    storage_error = (
        StoredImageNotFoundError("fixture input missing")
        if outcome == "terminal_failure"
        else None
    )
    storage = MutableStorage(error=storage_error)
    policy = PredictionRetryPolicy(3, 3, 60)
    token = worker_metrics.set(metrics)
    try:
        with metric_sessions() as db:
            job = create_prediction(db, created_at=now - timedelta(seconds=10))
            commit = db.commit
            calls = 0

            def delayed_commit():
                nonlocal calls, now
                calls += 1
                if calls != 2:
                    commit()
                    return
                now += timedelta(seconds=30)
                if outcome == "commit_rejected":
                    raise SQLAlchemyError("fixture commit rejected")
                commit()
                if outcome == "commit_unacknowledged":
                    raise SQLAlchemyError("fixture commit acknowledgement lost")

            monkeypatch.setattr(db, "commit", delayed_commit)
            process_next_prediction(db, successful_inference, storage, policy)
            assert job.status == expected_status
            if expected_status != PredictionStatus.PROCESSING.value:
                assert job.completed_at == settled_at
    finally:
        worker_metrics.reset(token)

    if terminal_observed:
        labels = {"status": expected_status}
        assert (
            metrics.registry.get_sample_value("vddai_job_terminal_total", labels) == 1
        )
        assert (
            metrics.registry.get_sample_value("vddai_job_duration_seconds_sum", labels)
            == 40
        )
        assert (
            metrics.registry.get_sample_value(
                "vddai_job_duration_seconds_bucket", {**labels, "le": "15.0"}
            )
            == 0
        )
    else:
        for status in ("completed", "failed"):
            assert (
                metrics.registry.get_sample_value(
                    "vddai_job_terminal_total", {"status": status}
                )
                == 0
            )
            assert (
                metrics.registry.get_sample_value(
                    "vddai_job_duration_seconds_count", {"status": status}
                )
                is None
            )


def test_recovery_failure_cannot_be_masked_by_idle_claim(
    metric_sessions,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 25, 10, 30)
    monkeypatch.setattr(prediction_worker, "_utc_now_naive", lambda: now)
    metrics = WorkerMetrics()
    policy = PredictionRetryPolicy(3, 5, 15)
    token = worker_metrics.set(metrics)
    try:
        with metric_sessions() as db:
            job = create_prediction(db, created_at=now - timedelta(seconds=30))
            job.start_processing(
                at=now - timedelta(seconds=20),
                lease_expires_at=now - timedelta(seconds=5),
            )
            db.commit()

            def fail_recovery():
                raise SQLAlchemyError("fixture recovery failed")

            with monkeypatch.context() as failed:
                failed.setattr(db, "commit", fail_recovery)
                assert not process_next_prediction(db, retry_policy=policy)
                assert job.next_attempt_at is None
                assert metrics.registry.get_sample_value("vddai_worker_ready") == 0

            assert not process_next_prediction(db, retry_policy=policy)
            assert job.next_attempt_at == now + timedelta(seconds=5)
            assert metrics.registry.get_sample_value("vddai_worker_ready") == 1
            assert (
                metrics.registry.get_sample_value("vddai_job_retries_scheduled_total")
                == 1
            )
    finally:
        worker_metrics.reset(token)
