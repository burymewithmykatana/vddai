import datetime as dt
import logging
import time
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contracts.inference import (
    AnomalyInferenceResult,
)
from app.db.session import SessionLocal
from app.models.prediction import Prediction, PredictionStatus
from app.services.anomaly_inference_service import get_anomaly_inference_service
from app.services.image_storage_service import image_storage_service

logger = logging.getLogger(__name__)


class InferenceService(Protocol):
    def predict(self, image_contents: bytes) -> AnomalyInferenceResult:
        """Return one frozen-package image-level prediction."""


class PredictionImageStorage(Protocol):
    def read(self, object_key: str) -> bytes:
        """Retrieve one prediction input by opaque object key."""


def _utc_now_naive() -> dt.datetime:
    """Match the repository's timezone-naive UTC database convention."""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _internal_failure_message(exc: Exception) -> str:
    detail = str(exc).strip()
    if not detail:
        return type(exc).__name__
    return f"{type(exc).__name__}: {detail}"[:2000]


def _mark_prediction_failed(
    db: Session,
    *,
    prediction_id: int,
    cause: Exception,
) -> bool:
    """Recover the transaction, then persist one clean terminal failure."""
    try:
        db.rollback()
        prediction = db.get(Prediction, prediction_id)
        if prediction is None:
            logger.error(
                "worker_failure_row_missing prediction_id=%s",
                prediction_id,
            )
            return False

        prediction.fail(
            error_message=_internal_failure_message(cause),
            at=_utc_now_naive(),
        )
        db.commit()
        return True
    except (SQLAlchemyError, ValueError):
        logger.exception(
            "worker_failed_to_persist_failure prediction_id=%s",
            prediction_id,
        )
        try:
            db.rollback()
        except SQLAlchemyError:
            logger.exception(
                "worker_failed_to_recover_session prediction_id=%s",
                prediction_id,
            )
        return False


def process_next_prediction(
    db: Session,
    inference_service: InferenceService | None = None,
    storage_service: PredictionImageStorage | None = None,
) -> bool:
    prediction = (
        db.query(Prediction)
        .filter(Prediction.status == PredictionStatus.QUEUED.value)
        .order_by(Prediction.created_at.asc(), Prediction.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )

    if prediction is None:
        logger.info("worker_no_queued_predictions")
        return False

    prediction_id = prediction.id
    image_object_key = prediction.image_object_key
    logger.info(
        "worker_started_prediction prediction_id=%s",
        prediction_id,
    )

    prediction.start_processing(at=_utc_now_naive())
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "worker_failed_to_claim_prediction prediction_id=%s",
            prediction_id,
        )
        return False

    try:
        service = inference_service or get_anomaly_inference_service()
        storage = storage_service or image_storage_service
        image_contents = storage.read(image_object_key)
        result = service.predict(image_contents)

        prediction.complete(result, at=_utc_now_naive())

        db.commit()

        logger.info(
            "worker_completed_prediction prediction_id=%s label=%s "
            "anomaly_score=%s threshold=%s model_version=%s latency_ms=%s",
            prediction_id,
            result.predicted_label.value,
            result.anomaly_score,
            result.threshold,
            result.model_version,
            result.latency_ms,
        )

        return True

    except Exception as exc:
        logger.exception(
            "worker_prediction_execution_failed prediction_id=%s",
            prediction_id,
        )
        _mark_prediction_failed(
            db,
            prediction_id=prediction_id,
            cause=exc,
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
