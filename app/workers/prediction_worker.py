import datetime as dt
import math
import time
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logging import (
    LogError,
    LogEvent,
    elapsed_ms,
    guard_service_startup,
    log_event,
    setup_logging,
)

with guard_service_startup("worker") if __name__ == "__main__" else nullcontext():
    from app.contracts.inference import AnomalyInferenceResult
    from app.db.session import SessionLocal
    from app.models.prediction import Prediction, PredictionStatus
    from app.services.anomaly_inference_service import get_anomaly_inference_service
    from app.services.image_preprocessing_service import ImagePreprocessingError
    from app.services.image_storage_service import (
        ImageStorageError,
        InvalidImageObjectKeyError,
        StoredImageNotFoundError,
        image_storage_service,
    )
    from app.services.metrics_service import (
        WorkerMetrics,
        log_metrics_failure,
        serve_metrics,
        worker_metrics,
    )
    from app.services.model_package_loader import ModelPackageError
    from app.services.promoted_model_resolver import PromotedModelResolutionError
    from app.services.quality_monitor import quality_observer, read_quality_reference


def _log(
    event: LogEvent,
    *,
    status: str,
    attempt: int | None = None,
    latency_ms: int | None = None,
    error_code: LogError | None = None,
    job_duration_seconds: float | None = None,
    **fields,
) -> None:
    log_event(
        event,
        service="worker",
        status=status,
        attempt=attempt,
        latency_ms=latency_ms,
        error_code=error_code,
        **fields,
    )
    metrics = worker_metrics.get()
    if metrics is not None:
        try:
            metrics.record_event(
                event,
                status=status,
                attempt=attempt,
                latency_ms=latency_ms,
                error_code=error_code,
                job_duration_seconds=job_duration_seconds,
            )
        except Exception:
            log_metrics_failure("worker")


def _job_duration_seconds(created_at: dt.datetime) -> float | None:
    if worker_metrics.get() is None:
        return None
    return max(0.0, (_utc_now_naive() - created_at).total_seconds())


class InferenceService(Protocol):
    def predict(self, image_contents: bytes) -> AnomalyInferenceResult:
        """Return one frozen-package image-level prediction."""


class PredictionImageStorage(Protocol):
    def read(self, object_key: str) -> bytes:
        """Retrieve one prediction input by opaque object key."""


@dataclass(frozen=True)
class PredictionRetryPolicy:
    max_attempts: int
    retry_delay_seconds: float
    attempt_lease_seconds: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
        ):
            raise ValueError("Worker max attempts must be at least one.")
        if (
            isinstance(self.retry_delay_seconds, bool)
            or not isinstance(self.retry_delay_seconds, (int, float))
            or not math.isfinite(self.retry_delay_seconds)
            or self.retry_delay_seconds <= 0
        ):
            raise ValueError("Worker retry delay must be positive.")
        if (
            isinstance(self.attempt_lease_seconds, bool)
            or not isinstance(self.attempt_lease_seconds, (int, float))
            or not math.isfinite(self.attempt_lease_seconds)
            or self.attempt_lease_seconds <= 0
        ):
            raise ValueError("Worker attempt lease must be positive.")

    def next_attempt_at(self, now: dt.datetime) -> dt.datetime:
        return now + dt.timedelta(seconds=self.retry_delay_seconds)

    def lease_expires_at(self, now: dt.datetime) -> dt.datetime:
        return now + dt.timedelta(seconds=self.attempt_lease_seconds)


@dataclass(frozen=True)
class ClaimedPrediction:
    prediction_id: int
    image_object_key: str
    attempt: int


def _log_attempt(
    event: LogEvent,
    claim: ClaimedPrediction,
    *,
    status: str,
    latency_ms: int,
    model_version: str | None = None,
    error_code: LogError | None = None,
    job_duration_seconds: float | None = None,
) -> None:
    _log(
        event,
        status=status,
        latency_ms=latency_ms,
        prediction_id=claim.prediction_id,
        attempt=claim.attempt,
        model_version=model_version,
        error_code=error_code,
        job_duration_seconds=job_duration_seconds,
    )


def _log_failure_outcome(
    action: str,
    *,
    prediction_id: int,
    attempt: int,
    started_ns: int,
    error_code: LogError,
    job_created_at: dt.datetime,
) -> None:
    retry = action == "retry_scheduled"
    _log(
        LogEvent.RETRY_SCHEDULED if retry else LogEvent.TERMINAL_COMMITTED,
        status=(
            PredictionStatus.PROCESSING.value
            if retry
            else PredictionStatus.FAILED.value
        ),
        latency_ms=elapsed_ms(started_ns),
        prediction_id=prediction_id,
        attempt=attempt,
        error_code=error_code,
        job_duration_seconds=None if retry else _job_duration_seconds(job_created_at),
    )


def _discard_attempt(
    db: Session,
    claim: ClaimedPrediction,
    started_ns: int,
    error_code: LogError,
) -> None:
    db.rollback()
    _log_attempt(
        LogEvent.ATTEMPT_DISCARDED,
        claim,
        status="discarded",
        latency_ms=elapsed_ms(started_ns),
        error_code=error_code,
    )


def _observe_settled_result(
    db: Session,
    prediction: Prediction,
    claim: ClaimedPrediction,
    started_ns: int,
) -> bool:
    same_attempt = prediction.attempt_count == claim.attempt
    status = prediction.status
    model_version = prediction.model_version
    if same_attempt:
        db.rollback()
        _log_attempt(
            LogEvent.RESULT_OBSERVED,
            claim,
            status=status,
            latency_ms=elapsed_ms(started_ns),
            model_version=model_version,
        )
    else:
        _discard_attempt(db, claim, started_ns, LogError.STALE_ATTEMPT)
    return same_attempt and status != PredictionStatus.FAILED.value


def _utc_now_naive() -> dt.datetime:
    """Match the repository's timezone-naive UTC database convention."""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _internal_failure_message(exc: Exception) -> str:
    detail = str(exc).strip()
    if not detail:
        return type(exc).__name__
    return f"{type(exc).__name__}: {detail}"[:2000]


def _configured_retry_policy() -> PredictionRetryPolicy:
    from app.core.config import settings

    return PredictionRetryPolicy(
        max_attempts=settings.WORKER_MAX_ATTEMPTS,
        retry_delay_seconds=settings.WORKER_RETRY_DELAY_SECONDS,
        attempt_lease_seconds=settings.WORKER_ATTEMPT_LEASE_SECONDS,
    )


def _lock_prediction(db: Session, prediction_id: int) -> Prediction | None:
    return (
        db.query(Prediction)
        .filter(Prediction.id == prediction_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )


def _is_current_active_attempt(
    prediction: Prediction,
    *,
    expected_attempt: int,
) -> bool:
    return (
        prediction.status == PredictionStatus.PROCESSING.value
        and prediction.processing_started_at is not None
        and prediction.attempt_count == expected_attempt
        and prediction.lease_expires_at is not None
        and prediction.next_attempt_at is None
    )


def _schedule_retry_or_fail_locked(
    prediction: Prediction,
    *,
    expected_attempt: int,
    cause: Exception,
    now: dt.datetime,
    retry_policy: PredictionRetryPolicy,
) -> str:
    failure_message = _internal_failure_message(cause)
    if prediction.attempt_count >= retry_policy.max_attempts:
        exhausted_message = (
            f"RetryExhausted after {prediction.attempt_count} attempts: "
            f"{failure_message}"
        )[:2000]
        prediction.fail(
            expected_attempt=expected_attempt,
            error_message=exhausted_message,
            at=now,
        )
        return "failed"

    prediction.schedule_retry(
        expected_attempt=expected_attempt,
        error_message=failure_message,
        next_attempt_at=retry_policy.next_attempt_at(now),
    )
    return "retry_scheduled"


def _recover_one_stale_prediction(
    db: Session,
    *,
    now: dt.datetime,
    retry_policy: PredictionRetryPolicy,
) -> bool:
    started_ns = time.perf_counter_ns()
    prediction = (
        db.query(Prediction)
        .filter(
            Prediction.status == PredictionStatus.PROCESSING.value,
            Prediction.processing_started_at.is_not(None),
            Prediction.next_attempt_at.is_(None),
            or_(
                Prediction.lease_expires_at <= now,
                Prediction.lease_expires_at.is_(None),
            ),
        )
        .order_by(Prediction.created_at.asc(), Prediction.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if prediction is None:
        return False

    prediction_id = prediction.id
    attempt = prediction.attempt_count
    action = _schedule_retry_or_fail_locked(
        prediction,
        expected_attempt=attempt,
        cause=RuntimeError("Worker attempt lease expired before settlement."),
        now=now,
        retry_policy=retry_policy,
    )
    job_created_at = prediction.created_at
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        _log(
            LogEvent.SETTLEMENT_FAILED,
            status="error",
            prediction_id=prediction_id,
            attempt=attempt,
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.RECOVERY_FAILED,
        )
        return False

    _log_failure_outcome(
        action,
        prediction_id=prediction_id,
        attempt=attempt,
        started_ns=started_ns,
        error_code=LogError.LEASE_EXPIRED,
        job_created_at=job_created_at,
    )
    return True


def _claim_next_prediction(
    db: Session,
    *,
    now: dt.datetime,
    retry_policy: PredictionRetryPolicy,
) -> ClaimedPrediction | None:
    started_ns = time.perf_counter_ns()
    prediction = (
        db.query(Prediction)
        .filter(
            or_(
                Prediction.status == PredictionStatus.QUEUED.value,
                and_(
                    Prediction.status == PredictionStatus.PROCESSING.value,
                    Prediction.lease_expires_at.is_(None),
                    Prediction.next_attempt_at.is_not(None),
                    Prediction.next_attempt_at <= now,
                ),
            )
        )
        .order_by(Prediction.created_at.asc(), Prediction.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if prediction is None:
        return None

    prediction_id = prediction.id
    image_object_key = prediction.image_object_key
    try:
        if (
            prediction.status == PredictionStatus.PROCESSING.value
            and prediction.attempt_count >= retry_policy.max_attempts
        ):
            attempt = prediction.attempt_count
            prediction.fail_retry_waiting(
                expected_attempt=attempt,
                error_message=(
                    f"RetryExhausted after {attempt} attempts: configured "
                    f"maximum is {retry_policy.max_attempts}."
                ),
                at=now,
            )
            job_created_at = prediction.created_at
            db.commit()
            _log_failure_outcome(
                "failed",
                prediction_id=prediction_id,
                attempt=attempt,
                started_ns=started_ns,
                error_code=LogError.RETRY_LIMIT,
                job_created_at=job_created_at,
            )
            return None
        attempt = prediction.start_processing(
            at=now,
            lease_expires_at=retry_policy.lease_expires_at(now),
        )
        db.commit()
    except (SQLAlchemyError, ValueError):
        db.rollback()
        _log(
            LogEvent.CLAIM,
            status="error",
            prediction_id=prediction_id,
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.CLAIM_FAILED,
        )
        return None

    _log(
        LogEvent.CLAIM,
        status=PredictionStatus.PROCESSING.value,
        prediction_id=prediction_id,
        attempt=attempt,
        latency_ms=elapsed_ms(started_ns),
    )
    return ClaimedPrediction(
        prediction_id=prediction_id,
        image_object_key=image_object_key,
        attempt=attempt,
    )


def _is_retryable_execution_failure(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            StoredImageNotFoundError,
            InvalidImageObjectKeyError,
            ImagePreprocessingError,
            PromotedModelResolutionError,
            ModelPackageError,
        ),
    ):
        return False
    return isinstance(exc, ImageStorageError)


def _settle_execution_failure(
    db: Session,
    *,
    claim: ClaimedPrediction,
    cause: Exception,
    retry_policy: PredictionRetryPolicy,
    now: dt.datetime,
    error_code: LogError,
) -> None:
    started_ns = time.perf_counter_ns()
    try:
        db.rollback()
        prediction = _lock_prediction(db, claim.prediction_id)
        if prediction is None:
            _discard_attempt(db, claim, started_ns, LogError.ROW_MISSING)
            return
        if prediction.status in {
            PredictionStatus.COMPLETED.value,
            PredictionStatus.NEEDS_REVIEW.value,
            PredictionStatus.FAILED.value,
        }:
            _observe_settled_result(db, prediction, claim, started_ns)
            return
        if not _is_current_active_attempt(
            prediction,
            expected_attempt=claim.attempt,
        ):
            _discard_attempt(db, claim, started_ns, LogError.STALE_ATTEMPT)
            return

        lease_expired = prediction.lease_expires_at <= now
        if lease_expired or _is_retryable_execution_failure(cause):
            action = _schedule_retry_or_fail_locked(
                prediction,
                expected_attempt=claim.attempt,
                cause=cause,
                now=now,
                retry_policy=retry_policy,
            )
        else:
            prediction.fail(
                expected_attempt=claim.attempt,
                error_message=_internal_failure_message(cause),
                at=now,
            )
            action = "failed"
        job_created_at = prediction.created_at
        db.commit()
        _log_failure_outcome(
            action,
            prediction_id=claim.prediction_id,
            attempt=claim.attempt,
            started_ns=started_ns,
            error_code=LogError.LEASE_EXPIRED if lease_expired else error_code,
            job_created_at=job_created_at,
        )
    except (SQLAlchemyError, ValueError):
        db.rollback()
        _log_attempt(
            LogEvent.SETTLEMENT_FAILED,
            claim,
            status="error",
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.SETTLEMENT_FAILED,
        )


def _reconcile_result_commit_error(
    db: Session,
    *,
    claim: ClaimedPrediction,
    cause: SQLAlchemyError,
    retry_policy: PredictionRetryPolicy,
    now: dt.datetime,
) -> bool:
    started_ns = time.perf_counter_ns()
    try:
        prediction = _lock_prediction(db, claim.prediction_id)
        if prediction is None:
            _discard_attempt(db, claim, started_ns, LogError.ROW_MISSING)
            return False
        if prediction.status in {
            PredictionStatus.COMPLETED.value,
            PredictionStatus.NEEDS_REVIEW.value,
            PredictionStatus.FAILED.value,
        }:
            return _observe_settled_result(db, prediction, claim, started_ns)
        if not _is_current_active_attempt(
            prediction,
            expected_attempt=claim.attempt,
        ):
            _discard_attempt(db, claim, started_ns, LogError.STALE_ATTEMPT)
            return False

        action = _schedule_retry_or_fail_locked(
            prediction,
            expected_attempt=claim.attempt,
            cause=cause,
            now=now,
            retry_policy=retry_policy,
        )
        job_created_at = prediction.created_at
        db.commit()
        _log_failure_outcome(
            action,
            prediction_id=claim.prediction_id,
            attempt=claim.attempt,
            started_ns=started_ns,
            error_code=LogError.RESULT_COMMIT_FAILED,
            job_created_at=job_created_at,
        )
    except (SQLAlchemyError, ValueError):
        db.rollback()
        _log_attempt(
            LogEvent.SETTLEMENT_FAILED,
            claim,
            status="error",
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.SETTLEMENT_FAILED,
        )
    return False


def _persist_success(
    db: Session,
    *,
    claim: ClaimedPrediction,
    result: AnomalyInferenceResult,
    retry_policy: PredictionRetryPolicy,
    now: dt.datetime,
) -> bool:
    started_ns = time.perf_counter_ns()
    try:
        prediction = _lock_prediction(db, claim.prediction_id)
        if prediction is None:
            _discard_attempt(db, claim, started_ns, LogError.ROW_MISSING)
            return False
        if prediction.status in {
            PredictionStatus.COMPLETED.value,
            PredictionStatus.NEEDS_REVIEW.value,
            PredictionStatus.FAILED.value,
        }:
            return _observe_settled_result(db, prediction, claim, started_ns)
        if not _is_current_active_attempt(
            prediction,
            expected_attempt=claim.attempt,
        ):
            _discard_attempt(db, claim, started_ns, LogError.STALE_ATTEMPT)
            return False
        if prediction.lease_expires_at <= now:
            action = _schedule_retry_or_fail_locked(
                prediction,
                expected_attempt=claim.attempt,
                cause=RuntimeError("Worker attempt lease expired before settlement."),
                now=now,
                retry_policy=retry_policy,
            )
            job_created_at = prediction.created_at
            db.commit()
            _log_failure_outcome(
                action,
                prediction_id=claim.prediction_id,
                attempt=claim.attempt,
                started_ns=started_ns,
                error_code=LogError.LEASE_EXPIRED,
                job_created_at=job_created_at,
            )
            return False

        prediction.complete(
            result,
            expected_attempt=claim.attempt,
            at=now,
        )
        status = prediction.status
        job_created_at = prediction.created_at
        db.commit()
        _log_attempt(
            LogEvent.TERMINAL_COMMITTED,
            claim,
            status=status,
            latency_ms=elapsed_ms(started_ns),
            model_version=result.model_version,
            job_duration_seconds=_job_duration_seconds(job_created_at),
        )
        return True
    except SQLAlchemyError as exc:
        db.rollback()
        _log_attempt(
            LogEvent.SETTLEMENT_FAILED,
            claim,
            status="error",
            latency_ms=elapsed_ms(started_ns),
            model_version=result.model_version,
            error_code=LogError.RESULT_COMMIT_FAILED,
        )
        return _reconcile_result_commit_error(
            db,
            claim=claim,
            cause=exc,
            retry_policy=retry_policy,
            now=now,
        )


def process_next_prediction(
    db: Session,
    inference_service: InferenceService | None = None,
    storage_service: PredictionImageStorage | None = None,
    retry_policy: PredictionRetryPolicy | None = None,
) -> bool:
    policy = retry_policy or _configured_retry_policy()
    metrics = worker_metrics.get()
    with metrics.observe_poll() if metrics is not None else nullcontext():
        started_ns = time.perf_counter_ns()
        try:
            _recover_one_stale_prediction(
                db,
                now=_utc_now_naive(),
                retry_policy=policy,
            )
        except (SQLAlchemyError, ValueError):
            db.rollback()
            _log(
                LogEvent.SETTLEMENT_FAILED,
                status="error",
                latency_ms=elapsed_ms(started_ns),
                error_code=LogError.RECOVERY_FAILED,
            )
            return False

        claim = _claim_next_prediction(
            db,
            now=_utc_now_naive(),
            retry_policy=policy,
        )
    if claim is None:
        return False

    operation = LogEvent.INFERENCE
    error_code = LogError.MODEL_UNAVAILABLE
    started_ns = time.perf_counter_ns()
    model_version = None
    try:
        service = inference_service or get_anomaly_inference_service()
        storage = storage_service or image_storage_service
        operation = LogEvent.STORAGE_READ
        error_code = LogError.STORAGE_READ_FAILED
        started_ns = time.perf_counter_ns()
        image_contents = storage.read(claim.image_object_key)
        _log_attempt(
            LogEvent.STORAGE_READ, claim, status="ok", latency_ms=elapsed_ms(started_ns)
        )

        operation = LogEvent.INFERENCE
        error_code = LogError.INFERENCE_FAILED
        started_ns = time.perf_counter_ns()
        result = service.predict(image_contents)
        model_version = result.model_version
        _log_attempt(
            LogEvent.INFERENCE,
            claim,
            status="ok",
            latency_ms=result.latency_ms,
            model_version=model_version,
        )

        operation = LogEvent.SETTLEMENT_FAILED
        error_code = LogError.SETTLEMENT_FAILED
        started_ns = time.perf_counter_ns()
        return _persist_success(
            db,
            claim=claim,
            result=result,
            retry_policy=policy,
            now=_utc_now_naive(),
        )

    except Exception as exc:
        _log_attempt(
            operation,
            claim,
            status="error",
            latency_ms=elapsed_ms(started_ns),
            model_version=model_version,
            error_code=error_code,
        )
        _settle_execution_failure(
            db,
            claim=claim,
            cause=exc,
            retry_policy=policy,
            now=_utc_now_naive(),
            error_code=error_code,
        )
        return False


def run_once() -> None:
    db = SessionLocal()

    try:
        process_next_prediction(db)
    finally:
        db.close()


def run_forever(poll_interval_seconds: float = 1.0) -> None:
    """Continuously process the database-backed queue in one worker process."""
    if poll_interval_seconds <= 0:
        raise ValueError("Worker poll interval must be positive.")

    _log(LogEvent.WORKER_STARTED, status="ok")
    while True:
        db = SessionLocal()
        try:
            was_processed = process_next_prediction(db)
        finally:
            db.close()

        if not was_processed:
            time.sleep(poll_interval_seconds)


def main() -> None:
    from app.core.config import settings

    setup_logging()
    try:

        def create_metrics() -> WorkerMetrics:
            return WorkerMetrics(
                read_quality_reference(
                    settings.METRICS_QUALITY_REFERENCE_FILE,
                    allow_synthetic=settings.ENVIRONMENT == "test",
                )
            )

        with serve_metrics(settings, "worker", create_metrics) as metrics:
            token = worker_metrics.set(metrics)
            quality_token = quality_observer.set(
                metrics.quality.observe if metrics else None
            )
            try:
                run_forever(settings.WORKER_POLL_INTERVAL_SECONDS)
            finally:
                quality_observer.reset(quality_token)
                worker_metrics.reset(token)
    except Exception:
        _log(
            LogEvent.WORKER_ERROR,
            status="error",
            error_code=LogError.WORKER_ERROR,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
