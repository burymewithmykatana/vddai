import json
import logging
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter_ns
from typing import Literal


class LogEvent(StrEnum):
    HTTP_REQUEST = "http.request_finished"
    STORAGE_WRITE = "storage.write_finished"
    STORAGE_READ = "storage.read_finished"
    STORAGE_CLEANUP = "storage.orphan_cleanup"
    ENQUEUE = "prediction.enqueue"
    READBACK = "prediction.readback"
    CLAIM = "prediction.claim"
    INFERENCE = "prediction.inference"
    RETRY_SCHEDULED = "prediction.retry_scheduled"
    TERMINAL_COMMITTED = "prediction.terminal_committed"
    RESULT_OBSERVED = "prediction.result_observed"
    SETTLEMENT_FAILED = "prediction.settlement_failed"
    ATTEMPT_DISCARDED = "prediction.attempt_discarded"
    WORKER_STARTED = "worker.started"
    WORKER_ERROR = "worker.error"
    SERVER_ERROR = "server.error"
    STARTUP_FAILED = "service.startup_failed"
    METRICS_UNAVAILABLE = "service.metrics_unavailable"


class LogError(StrEnum):
    REQUEST_FAILED = "request_failed"
    SERVER_ERROR = "server_error"
    RATE_LIMITED = "rate_limited"
    ADMISSION_UNAVAILABLE = "admission_unavailable"
    USER_CAPACITY = "user_capacity"
    GLOBAL_CAPACITY = "global_capacity"
    ENQUEUE_FAILED = "enqueue_failed"
    UPLOAD_REJECTED = "upload_rejected"
    STORAGE_WRITE_FAILED = "storage_write_failed"
    STORAGE_CLEANUP_FAILED = "storage_cleanup_failed"
    STORAGE_READ_FAILED = "storage_read_failed"
    MODEL_UNAVAILABLE = "model_unavailable"
    INFERENCE_FAILED = "inference_failed"
    CLAIM_FAILED = "claim_failed"
    RECOVERY_FAILED = "recovery_failed"
    LEASE_EXPIRED = "lease_expired"
    RETRY_LIMIT = "retry_limit"
    ROW_MISSING = "row_missing"
    STALE_ATTEMPT = "stale_attempt"
    RESULT_COMMIT_FAILED = "result_commit_failed"
    SETTLEMENT_FAILED = "settlement_failed"
    WORKER_ERROR = "worker_error"
    STARTUP_FAILED = "startup_failed"
    METRICS_UNAVAILABLE = "metrics_unavailable"


request_id_context: ContextVar[str | None] = ContextVar(
    "vddai_request_id", default=None
)
_logger = logging.getLogger("vddai.lifecycle")
_request_id = re.compile(r"[0-9a-f]{32}")
_package_id = re.compile(r"[a-z0-9][a-z0-9-]{7,99}")
_route_template = re.compile(r"/[a-zA-Z0-9_/{}\-.]{0,127}")
_methods = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
_statuses = frozenset(
    {
        "ok",
        "rejected",
        "error",
        "discarded",
        "queued",
        "processing",
        "completed",
        "failed",
        "needs_review",
    }
)


def elapsed_ms(started_ns: int) -> int:
    return (perf_counter_ns() - started_ns) // 1_000_000


def log_event(
    event: LogEvent,
    *,
    service: Literal["api", "worker"],
    status: str,
    latency_ms: int | None = None,
    prediction_id: int | None = None,
    attempt: int | None = None,
    model_version: str | None = None,
    error_code: LogError | None = None,
    method: str | None = None,
    route: str | None = None,
    http_status: int | None = None,
) -> None:
    """Write a bounded event without formatting raw requests or exceptions."""
    if not isinstance(event, LogEvent) or service not in ("api", "worker"):
        return
    request_id = request_id_context.get() if service == "api" else None
    prediction_id = (
        prediction_id if type(prediction_id) is int and prediction_id > 0 else None
    )
    level = logging.WARNING if error_code is not None else logging.INFO
    record = {
        "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "schema_version": 1,
        "level": logging.getLevelName(level),
        "service": service,
        "event": event.value,
        "request_id": (
            request_id
            if isinstance(request_id, str) and _request_id.fullmatch(request_id)
            else None
        ),
        "prediction_id": prediction_id,
        "job_id": prediction_id,
        "attempt": attempt if type(attempt) is int and attempt >= 0 else None,
        "model_version": (
            model_version
            if isinstance(model_version, str) and _package_id.fullmatch(model_version)
            else None
        ),
        "status": status if isinstance(status, str) and status in _statuses else None,
        "latency_ms": (
            latency_ms if type(latency_ms) is int and latency_ms >= 0 else None
        ),
        "error_code": error_code.value if isinstance(error_code, LogError) else None,
        "method": method if method in _methods else None,
        "route": (
            route
            if isinstance(route, str) and _route_template.fullmatch(route)
            else None
        ),
        "http_status": (
            http_status
            if type(http_status) is int and 100 <= http_status < 600
            else None
        ),
    }
    _logger.log(level, "%s", json.dumps(record, separators=(",", ":")))


class _SafeServerErrors(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.levelno < logging.WARNING
            and not record.exc_info
            and not record.exc_text
            and not record.stack_info
        ):
            return True
        log_event(
            LogEvent.SERVER_ERROR,
            service="api",
            status="error",
            error_code=LogError.SERVER_ERROR,
        )
        return False


class _StdoutHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stdout.write(record.getMessage() + "\n")
            sys.stdout.flush()
        except (OSError, ValueError):
            # Output may be unavailable during shutdown. Logging must not change
            # the outcome of a request or a database transaction.
            pass


_safe_server_errors = _SafeServerErrors()
_stdout_handler = _StdoutHandler()


def setup_logging(*, api: bool = False) -> None:
    """Configure the application-owned logger at the process entry point."""
    _logger.addHandler(_stdout_handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False
    _logger.disabled = False
    if api:
        logging.getLogger("uvicorn.access").disabled = True
        logging.getLogger("uvicorn.error").addFilter(_safe_server_errors)


@contextmanager
def guard_service_startup(service: Literal["api", "worker"]) -> Iterator[None]:
    """Report a failed service import without rendering its configuration."""
    try:
        yield
    except Exception:
        setup_logging()
        log_event(
            LogEvent.STARTUP_FAILED,
            service=service,
            status="error",
            error_code=LogError.STARTUP_FAILED,
        )
        raise SystemExit(1) from None
