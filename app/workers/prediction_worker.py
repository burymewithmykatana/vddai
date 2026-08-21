import datetime as dt
import logging
import math
import time
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contracts.inference import (
    AnomalyInferenceResult,
)
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
from app.services.model_package_loader import ModelPackageError
from app.services.promoted_model_resolver import PromotedModelResolutionError

logger = logging.getLogger(__name__)


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
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "worker_failed_to_recover_stale_prediction prediction_id=%s attempt=%s",
            prediction_id,
            attempt,
        )
        return False

    logger.warning(
        "worker_recovered_stale_prediction prediction_id=%s attempt=%s action=%s",
        prediction_id,
        attempt,
        action,
    )
    return True


def _claim_next_prediction(
    db: Session,
    *,
    now: dt.datetime,
    retry_policy: PredictionRetryPolicy,
) -> ClaimedPrediction | None:
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
            db.commit()
            logger.warning(
                "worker_retry_limit_reduced prediction_id=%s attempt=%s "
                "max_attempts=%s",
                prediction_id,
                attempt,
                retry_policy.max_attempts,
            )
            return None
        attempt = prediction.start_processing(
            at=now,
            lease_expires_at=retry_policy.lease_expires_at(now),
        )
        db.commit()
    except (SQLAlchemyError, ValueError):
        db.rollback()
        logger.exception(
            "worker_failed_to_claim_prediction prediction_id=%s",
            prediction_id,
        )
        return None

    logger.info(
        "worker_started_prediction prediction_id=%s attempt=%s",
        prediction_id,
        attempt,
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
) -> None:
    try:
        db.rollback()
        prediction = _lock_prediction(db, claim.prediction_id)
        if prediction is None:
            logger.error(
                "worker_failure_row_missing prediction_id=%s attempt=%s",
                claim.prediction_id,
                claim.attempt,
            )
            db.rollback()
            return
        if prediction.status in {
            PredictionStatus.COMPLETED.value,
            PredictionStatus.NEEDS_REVIEW.value,
            PredictionStatus.FAILED.value,
        }:
            logger.info(
                "worker_failure_already_settled prediction_id=%s attempt=%s status=%s",
                claim.prediction_id,
                claim.attempt,
                prediction.status,
            )
            db.rollback()
            return
        if not _is_current_active_attempt(
            prediction,
            expected_attempt=claim.attempt,
        ):
            logger.warning(
                "worker_discarded_stale_failure prediction_id=%s attempt=%s",
                claim.prediction_id,
                claim.attempt,
            )
            db.rollback()
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
        db.commit()
        logger.warning(
            "worker_prediction_failure_settled prediction_id=%s attempt=%s action=%s",
            claim.prediction_id,
            claim.attempt,
            action,
        )
    except (SQLAlchemyError, ValueError):
        logger.exception(
            "worker_failed_to_persist_failure prediction_id=%s attempt=%s",
            claim.prediction_id,
            claim.attempt,
        )
        db.rollback()


def _reconcile_result_commit_error(
    db: Session,
    *,
    claim: ClaimedPrediction,
    cause: SQLAlchemyError,
    retry_policy: PredictionRetryPolicy,
    now: dt.datetime,
) -> bool:
    try:
        prediction = _lock_prediction(db, claim.prediction_id)
        if prediction is None:
            db.rollback()
            return False
        if prediction.status in {
            PredictionStatus.COMPLETED.value,
            PredictionStatus.NEEDS_REVIEW.value,
        }:
            is_same_attempt = prediction.attempt_count == claim.attempt
            db.rollback()
            logger.info(
                "worker_result_commit_already_settled prediction_id=%s attempt=%s "
                "is_same_attempt=%s",
                claim.prediction_id,
                claim.attempt,
                is_same_attempt,
            )
            return is_same_attempt
        if prediction.status == PredictionStatus.FAILED.value:
            db.rollback()
            return False
        if not _is_current_active_attempt(
            prediction,
            expected_attempt=claim.attempt,
        ):
            db.rollback()
            return False

        action = _schedule_retry_or_fail_locked(
            prediction,
            expected_attempt=claim.attempt,
            cause=cause,
            now=now,
            retry_policy=retry_policy,
        )
        db.commit()
        logger.warning(
            "worker_result_commit_reconciled prediction_id=%s attempt=%s action=%s",
            claim.prediction_id,
            claim.attempt,
            action,
        )
    except (SQLAlchemyError, ValueError):
        logger.exception(
            "worker_failed_to_reconcile_result_commit prediction_id=%s attempt=%s",
            claim.prediction_id,
            claim.attempt,
        )
        db.rollback()
    return False


def _persist_success(
    db: Session,
    *,
    claim: ClaimedPrediction,
    result: AnomalyInferenceResult,
    retry_policy: PredictionRetryPolicy,
    now: dt.datetime,
) -> bool:
    try:
        prediction = _lock_prediction(db, claim.prediction_id)
        if prediction is None:
            db.rollback()
            return False
        if prediction.status in {
            PredictionStatus.COMPLETED.value,
            PredictionStatus.NEEDS_REVIEW.value,
        }:
            is_same_attempt = prediction.attempt_count == claim.attempt
            db.rollback()
            return is_same_attempt
        if prediction.status == PredictionStatus.FAILED.value:
            db.rollback()
            return False
        if not _is_current_active_attempt(
            prediction,
            expected_attempt=claim.attempt,
        ):
            logger.warning(
                "worker_discarded_stale_result prediction_id=%s attempt=%s",
                claim.prediction_id,
                claim.attempt,
            )
            db.rollback()
            return False
        if prediction.lease_expires_at <= now:
            action = _schedule_retry_or_fail_locked(
                prediction,
                expected_attempt=claim.attempt,
                cause=RuntimeError("Worker attempt lease expired before settlement."),
                now=now,
                retry_policy=retry_policy,
            )
            db.commit()
            logger.warning(
                "worker_discarded_expired_result prediction_id=%s attempt=%s action=%s",
                claim.prediction_id,
                claim.attempt,
                action,
            )
            return False

        prediction.complete(
            result,
            expected_attempt=claim.attempt,
            at=now,
        )
        db.commit()
        return True
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception(
            "worker_result_commit_failed prediction_id=%s attempt=%s",
            claim.prediction_id,
            claim.attempt,
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
    try:
        _recover_one_stale_prediction(
            db,
            now=_utc_now_naive(),
            retry_policy=policy,
        )
    except (SQLAlchemyError, ValueError):
        logger.exception("worker_stale_recovery_failed")
        db.rollback()
        return False

    claim = _claim_next_prediction(
        db,
        now=_utc_now_naive(),
        retry_policy=policy,
    )
    if claim is None:
        logger.info("worker_no_queued_predictions")
        return False

    try:
        service = inference_service or get_anomaly_inference_service()
        storage = storage_service or image_storage_service
        image_contents = storage.read(claim.image_object_key)
        result = service.predict(image_contents)
        was_completed = _persist_success(
            db,
            claim=claim,
            result=result,
            retry_policy=policy,
            now=_utc_now_naive(),
        )
        if not was_completed:
            return False
        logger.info(
            "worker_completed_prediction prediction_id=%s attempt=%s label=%s "
            "anomaly_score=%s threshold=%s model_version=%s latency_ms=%s",
            claim.prediction_id,
            claim.attempt,
            result.predicted_label.value,
            result.anomaly_score,
            result.threshold,
            result.model_version,
            result.latency_ms,
        )

        return True

    except Exception as exc:
        logger.exception(
            "worker_prediction_execution_failed prediction_id=%s attempt=%s",
            claim.prediction_id,
            claim.attempt,
        )
        _settle_execution_failure(
            db,
            claim=claim,
            cause=exc,
            retry_policy=policy,
            now=_utc_now_naive(),
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

    logger.info(
        "prediction_worker_started poll_interval_seconds=%s",
        poll_interval_seconds,
    )
    while True:
        db = SessionLocal()
        try:
            was_processed = process_next_prediction(db)
        finally:
            db.close()

        if not was_processed:
            time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    from app.core.config import settings

    run_forever(settings.WORKER_POLL_INTERVAL_SECONDS)
