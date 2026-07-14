import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.prediction import Prediction, PredictionStatus
from app.services.mock_model_service import mock_model_service

logger = logging.getLogger(__name__)


def process_next_prediction(db: Session) -> bool:
    prediction = (
        db.query(Prediction)
        .filter(Prediction.status == PredictionStatus.QUEUED.value)
        .order_by(Prediction.created_at.asc())
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
        result = mock_model_service.predict(prediction.image_path)

        prediction.predicted_label = result["predicted_label"]
        prediction.confidence = result["confidence"]
        prediction.model_version = result["model_version"]
        prediction.latency_ms = result["latency_ms"]
        prediction.threshold = 0.75
        prediction.status = PredictionStatus.COMPLETED.value
        prediction.completed_at = datetime.utcnow()
        prediction.error_message = None

        db.commit()
        db.refresh(prediction)

        logger.info(
            "worker_completed_prediction prediction_id=%s label=%s confidence=%s latency_ms=%s",
            prediction.id,
            prediction.predicted_label,
            prediction.confidence,
            prediction.latency_ms,
        )

        return True

    except Exception as exc:
        prediction.status = PredictionStatus.FAILED.value
        prediction.error_message = str(exc)
        prediction.completed_at = datetime.utcnow()

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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    run_once()
