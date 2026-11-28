"""Opt-in, process-local metrics for the API and prediction worker."""

import socket
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv4Network
from threading import Lock, Thread
from typing import Literal, Protocol
from wsgiref.simple_server import WSGIRequestHandler, make_server

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    make_wsgi_app,
)
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.exposition import ThreadingWSGIServer
from sqlalchemy import case, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import LogError, LogEvent, log_event
from app.models.prediction import Prediction, PredictionStatus
from app.services.image_storage_service import StoredImage
from app.services.quality_monitor import (
    DIMENSION_BOUNDS,
    QualityReference,
    QualityWindow,
    monitored_format,
)

HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
QUEUE_STATES = ("queued", "active", "retry_waiting")
PRIVATE_NETWORKS = tuple(
    IPv4Network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
REQUEST_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10)
INFERENCE_BUCKETS = (*REQUEST_BUCKETS, 30)
JOB_BUCKETS = (0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300)
EXECUTION_FAILURE_STAGES = {
    LogError.MODEL_UNAVAILABLE: "model",
    LogError.STORAGE_READ_FAILED: "storage",
    LogError.INFERENCE_FAILED: "inference",
}
TERMINAL_STATES = ("completed", "failed", "needs_review")


class QueueCollector:
    """Read queue state without claiming or updating jobs."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._snapshot_lock = Lock()

    def collect(self) -> Iterator[GaugeMetricFamily]:
        ready = GaugeMetricFamily(
            "vddai_database_ready", "The queue snapshot succeeded."
        )
        state = case(
            (Prediction.status == PredictionStatus.QUEUED.value, "queued"),
            (Prediction.next_attempt_at.is_not(None), "retry_waiting"),
            else_="active",
        ).label("queue_state")
        query = (
            select(state, func.count(), func.min(Prediction.created_at))
            .where(
                Prediction.status.in_(
                    (PredictionStatus.QUEUED.value, PredictionStatus.PROCESSING.value)
                )
            )
            .group_by("queue_state")
        )
        if not self._snapshot_lock.acquire(blocking=False):
            return
        try:
            with self._session_factory() as session:
                if session.get_bind().dialect.name == "postgresql":
                    session.execute(text("SET LOCAL statement_timeout = '1000ms'"))
                rows = session.execute(query).all()
        except SQLAlchemyError:
            rows = None
        finally:
            self._snapshot_lock.release()

        ready.add_metric([], int(rows is not None))
        yield ready
        if rows is None:
            return
        depth = GaugeMetricFamily(
            "vddai_queue_depth", "Outstanding predictions by state.", labels=["state"]
        )
        age = GaugeMetricFamily(
            "vddai_queue_oldest_age_seconds",
            "Seconds since the oldest prediction in the state was accepted.",
            labels=["state"],
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        snapshot = {queue_state: (count, oldest) for queue_state, count, oldest in rows}
        for queue_state in QUEUE_STATES:
            count, oldest = snapshot.get(queue_state, (0, None))
            seconds = max(0.0, (now - oldest).total_seconds()) if oldest else 0.0
            depth.add_metric([queue_state], count)
            age.add_metric([queue_state], seconds)
        yield depth
        yield age


class ApiMetrics:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.registry = CollectorRegistry()
        labels = ("method", "route", "status_class")
        self._requests = Counter(
            "vddai_http_requests_total",
            "Observed HTTP request outcomes.",
            labels,
            registry=self.registry,
        )
        self._duration = Histogram(
            "vddai_http_request_duration_seconds",
            "Time spent handling HTTP requests.",
            labels,
            buckets=REQUEST_BUCKETS,
            registry=self.registry,
        )
        self._upload_formats = Counter(
            "vddai_upload_accepted_total",
            "Committed uploads by validated image format.",
            ("format",),
            registry=self.registry,
        )
        self._upload_dimensions = Histogram(
            "vddai_upload_dimension_pixels",
            "Original image dimension of committed uploads.",
            ("axis",),
            buckets=DIMENSION_BOUNDS,
            registry=self.registry,
        )
        self._upload_rejected = Counter(
            "vddai_upload_validation_rejected_total",
            "Image validation rejections by bounded HTTP status.",
            ("status",),
            registry=self.registry,
        )
        Gauge(
            "vddai_api_ready", "The API has completed startup.", registry=self.registry
        ).set(1)
        self.registry.register(QueueCollector(session_factory))

    def record_upload(self, image: StoredImage) -> None:
        self._upload_formats.labels(monitored_format(image.format)).inc()
        self._upload_dimensions.labels("width").observe(image.width)
        self._upload_dimensions.labels("height").observe(image.height)

    def record_rejected_upload(self, status: int) -> None:
        self._upload_rejected.labels(
            str(status) if status in (400, 413, 415) else "other"
        ).inc()

    def record_request(
        self,
        method: str,
        route: str | None,
        status: int | None,
        elapsed_ms: int,
        *,
        finished: bool,
    ) -> None:
        bounded_method = method if method in HTTP_METHODS else "OTHER"
        status_class = "5xx"
        if finished and status is not None and 100 <= status < 600:
            status_class = f"{status // 100}xx"
        labels = (bounded_method, route or "unmatched", status_class)
        self._requests.labels(*labels).inc()
        self._duration.labels(*labels).observe(elapsed_ms / 1000)


class WorkerMetrics:
    def __init__(self, quality_reference: QualityReference | None = None) -> None:
        self.registry = registry = CollectorRegistry()
        self.quality = QualityWindow(quality_reference)
        registry.register(self.quality)
        self._ready = Gauge(
            "vddai_worker_ready",
            "The latest observed queue poll succeeded.",
            registry=registry,
        )
        self._poll_failed = False
        self._model_ready = Gauge(
            "vddai_worker_model_ready",
            "Observed readiness of the serving package.",
            registry=registry,
        )
        self._model_ready.set(float("nan"))
        self._claims = Counter(
            "vddai_job_claims_total",
            "Committed worker claims.",
            ("kind",),
            registry=registry,
        )
        self._retries = Counter(
            "vddai_job_retries_scheduled_total",
            "Committed retry schedules.",
            registry=registry,
        )
        self._terminal = Counter(
            "vddai_job_terminal_total",
            "Observed terminal commits.",
            ("status",),
            registry=registry,
        )
        self._job_duration = Histogram(
            "vddai_job_duration_seconds",
            "Time from queue acceptance to terminal result.",
            ("status",),
            buckets=JOB_BUCKETS,
            registry=registry,
        )
        self._inference = Histogram(
            "vddai_inference_duration_seconds",
            "Latency of successful inference.",
            buckets=INFERENCE_BUCKETS,
            registry=registry,
        )
        self._failure = Counter(
            "vddai_job_execution_failures_total",
            "Failed attempts by execution stage.",
            ("stage",),
            registry=registry,
        )
        for status in TERMINAL_STATES:
            self._terminal.labels(status)
        for stage in EXECUTION_FAILURE_STAGES.values():
            self._failure.labels(stage)

    @contextmanager
    def observe_poll(self) -> Iterator[None]:
        self._poll_failed = False
        try:
            yield
        except BaseException:
            self._poll_failed = True
            raise
        finally:
            try:
                self._ready.set(int(not self._poll_failed))
            except Exception:
                log_metrics_failure("worker")

    def record_event(
        self,
        event: LogEvent,
        *,
        status: str,
        attempt: int | None,
        latency_ms: int | None,
        error_code: LogError | None,
        job_duration_seconds: float | None,
    ) -> None:
        if error_code in (LogError.RECOVERY_FAILED, LogError.CLAIM_FAILED):
            self._poll_failed = True
        if event == LogEvent.CLAIM and status == PredictionStatus.PROCESSING.value:
            self._claims.labels("retry" if attempt and attempt > 1 else "initial").inc()
        elif event == LogEvent.RETRY_SCHEDULED:
            self._retries.inc()
        elif event == LogEvent.TERMINAL_COMMITTED:
            if status in TERMINAL_STATES:
                self._terminal.labels(status).inc()
                if job_duration_seconds is not None:
                    self._job_duration.labels(status).observe(job_duration_seconds)
        elif event == LogEvent.INFERENCE and status == "ok" and latency_ms is not None:
            self._model_ready.set(1)
            self._inference.observe(latency_ms / 1000)
        elif (
            event in (LogEvent.STORAGE_READ, LogEvent.INFERENCE)
            and error_code in EXECUTION_FAILURE_STAGES
        ):
            self._failure.labels(EXECUTION_FAILURE_STAGES[error_code]).inc()
            if error_code == LogError.MODEL_UNAVAILABLE:
                self._model_ready.set(0)


worker_metrics: ContextVar[WorkerMetrics | None] = ContextVar(
    "worker_metrics", default=None
)


class MetricsRegistry(Protocol):
    registry: CollectorRegistry


class _MetricsRequestHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def _bind_address(mode: Literal["loopback", "container"]) -> str:
    if mode == "loopback":
        return "127.0.0.1"
    address = IPv4Address(socket.gethostbyname(socket.gethostname()))
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError("Metrics require a private IPv4 container interface.")
    return str(address)


def log_metrics_failure(service: Literal["api", "worker"]) -> None:
    log_event(
        LogEvent.METRICS_UNAVAILABLE,
        service=service,
        status="error",
        error_code=LogError.METRICS_UNAVAILABLE,
    )


@contextmanager
def serve_metrics[T: MetricsRegistry](
    settings: Settings,
    service: Literal["api", "worker"],
    factory: Callable[[], T],
) -> Iterator[T | None]:
    """Keep the listener off public application ports and scoped to its process."""
    if not settings.METRICS_ENABLED:
        yield None
        return
    server = None
    try:
        metrics = factory()
        port = (
            settings.METRICS_API_PORT
            if service == "api"
            else settings.METRICS_WORKER_PORT
        )
        server = make_server(
            _bind_address(settings.METRICS_BIND_MODE),
            port,
            make_wsgi_app(metrics.registry),
            server_class=ThreadingWSGIServer,
            handler_class=_MetricsRequestHandler,
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
    except (OSError, RuntimeError, ValueError):
        if server is not None:
            server.server_close()
        log_metrics_failure(service)
        yield None
        return
    try:
        yield metrics
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
