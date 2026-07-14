import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.prediction import Prediction, PredictionStatus
from app.models.user import User
from app.schemas import PredictionQueuedResponse, PredictionRead
from app.services.image_storage_service import image_storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post(
    "",
    response_model=PredictionQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_prediction_job(
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PredictionQueuedResponse:
    image_path = image_storage_service.save(image)

    prediction = Prediction(
        user_id=current_user.id,
        image_path=image_path,
        status=PredictionStatus.QUEUED.value,
        model_version="mock-v1",
    )

    db.add(prediction)

    try:
        db.commit()
        db.refresh(prediction)
    except Exception:
        db.rollback()

        try:
            image_storage_service.delete(image_path)
        except OSError:
            logger.exception(
                "failed_to_delete_orphaned_image image_path=%s",
                image_path,
            )

        raise

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PredictionRead:
    prediction = db.get(Prediction, prediction_id)

    if prediction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prediction job not found.",
        )

    if prediction.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prediction job not found.",
        )

    return prediction
