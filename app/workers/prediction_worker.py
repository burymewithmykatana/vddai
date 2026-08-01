import datetime as dt
import logging
import time
from typing import Protocol

from sqlalchemy.orm import Session

from app.contracts.inference import (
    AnomalyInferenceResult,
)
from app.db.session import SessionLocal
from app.models.prediction import Prediction, PredictionStatus
from app.services.anomaly_inference_service import get_anomaly_inference_service

logger = logging.getLogger(__name__)


class InferenceService(Protocol):
    def predict(self, image_path: str) -> AnomalyInferenceResult:
        """Return one frozen-package image-level prediction."""


def process_next_prediction(
    db: Session,
    inference_service: InferenceService | None = None,
) -> bool:
    prediction = (
        db.query(Prediction)
        .filter(Prediction.status == PredictionStatus.QUEUED.value)
        .order_by(Prediction.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )

    if prediction is None:
        logger.info("worker_no_queued_predictions")
        return False

    logger.info(
        "worker_started_prediction prediction_id=%s image_path=%s",
        prediction.id,
        prediction.image_path,
    )

    prediction.status = PredictionStatus.PROCESSING.value
    db.commit()
    db.refresh(prediction)

    try:
        service = inference_service or get_anomaly_inference_service()
        result = service.predict(prediction.image_path)

        prediction.predicted_label = result.predicted_label
        prediction.anomaly_score = result.anomaly_score
        prediction.confidence = None
        prediction.model_version = result.model_version
        prediction.model_lineage = result.lineage_for_persistence()
        prediction.latency_ms = result.latency_ms
        prediction.threshold = result.threshold
        prediction.status = PredictionStatus.COMPLETED.value
        prediction.completed_at = dt.datetime.now(dt.UTC)
        prediction.error_message = None

        db.commit()
        db.refresh(prediction)

        logger.info(
            "worker_completed_prediction prediction_id=%s label=%s "
            "anomaly_score=%s threshold=%s model_version=%s latency_ms=%s",
            prediction.id,
            prediction.predicted_label,
            prediction.anomaly_score,
            prediction.threshold,
            prediction.model_version,
            prediction.latency_ms,
        )

        return True

    except Exception as exc:
        prediction.status = PredictionStatus.FAILED.value
        prediction.error_message = str(exc)
        prediction.completed_at = dt.datetime.now(dt.UTC)

        db.commit()

        logger.exception(
            "worker_failed_prediction prediction_id=%s",
            prediction.id,
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
