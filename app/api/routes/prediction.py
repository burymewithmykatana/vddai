import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.prediction import Prediction, PredictionStatus
from app.models.user import User
from app.schemas import PredictionCreate, PredictionQueuedResponse, PredictionRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post(
    "",
    response_model=PredictionQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_prediction_job(
    payload: PredictionCreate,
    db: Session = Depends(get_db),
) -> PredictionQueuedResponse:
    user = db.get(User, payload.user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    prediction = Prediction(
        user_id=payload.user_id,
        image_path=payload.image_path,
        status=PredictionStatus.QUEUED.value,
        model_version="mock-v1",
    )

    db.add(prediction)
    db.commit()
    db.refresh(prediction)

    logger.info(
        "prediction_job_created prediction_id=%s user_id=%s image_path=%s",
        prediction.id,
        prediction.user_id,
        prediction.image_path,
    )

    return PredictionQueuedResponse(
        prediction_id=prediction.id,
        status=prediction.status,
        message="Prediction job queued successfully.",
    )


@router.get("/{prediction_id}", response_model=PredictionRead)
def get_prediction_job(
    prediction_id: int,
    db: Session = Depends(get_db),
) -> PredictionRead:
    prediction = db.get(Prediction, prediction_id)

    if prediction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prediction job not found.",
        )

    return prediction
