import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
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
    stored_image = image_storage_service.store(image)

    try:
        prediction = Prediction(
            user_id=current_user.id,
            image_object_key=stored_image.object_key,
            image_format=stored_image.format,
            image_width=stored_image.width,
            image_height=stored_image.height,
            status=PredictionStatus.QUEUED.value,
        )
        db.add(prediction)
        db.commit()
    except Exception:
        db.rollback()

        try:
            image_storage_service.delete(stored_image.object_key)
        except Exception:
            logger.exception(
                "failed_to_delete_orphaned_image object_key=%s",
                stored_image.object_key,
            )

        raise

    db.refresh(prediction)

    logger.info(
        "prediction_job_created prediction_id=%s user_id=%s"
        " image_object_key=%s image_format=%s image_width=%s image_height=%s",
        prediction.id,
        prediction.user_id,
        prediction.image_object_key,
        prediction.image_format,
        prediction.image_width,
        prediction.image_height,
    )

    return PredictionQueuedResponse(
        prediction_id=prediction.id,
        status=prediction.status,
        message="Prediction job queued successfully.",
    )


@router.get("", response_model=list[PredictionRead])
def list_prediction_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[PredictionRead]:
    query = db.query(Prediction)
    if not current_user.is_admin:
        query = query.filter(Prediction.user_id == current_user.id)

    return (
        query.order_by(
            Prediction.created_at.desc(),
            Prediction.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
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
