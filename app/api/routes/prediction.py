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
from app.core.config import settings
from app.models.prediction import Prediction, PredictionStatus
from app.models.user import User
from app.schemas import PredictionQueuedResponse, PredictionRead
from app.services.image_storage_service import image_storage_service
from app.services.prediction_admission_service import (
    PredictionAdmissionUnavailableError,
    PredictionGlobalCapacityExceededError,
    PredictionRequestRateExceededError,
    PredictionUserOutstandingExceededError,
    prediction_admission_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions", tags=["predictions"])


def _retry_after_header(seconds: int) -> dict[str, str]:
    return {"Retry-After": str(seconds)}


def _delete_orphaned_image(object_key: str) -> None:
    try:
        image_storage_service.delete(object_key)
    except Exception:
        logger.exception(
            "failed_to_delete_orphaned_image object_key=%s",
            object_key,
        )


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
    user_id = current_user.id
    try:
        prediction_admission_service.consume_request_slot(
            db,
            user_id=user_id,
        )
        db.commit()
    except PredictionRequestRateExceededError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Prediction request rate limit exceeded. Retry later.",
            headers=_retry_after_header(exc.retry_after_seconds),
        ) from exc
    except PredictionAdmissionUnavailableError as exc:
        db.rollback()
        logger.exception("prediction_rate_admission_unavailable user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction service is temporarily unavailable. Retry later.",
            headers=_retry_after_header(
                settings.PREDICTION_CAPACITY_RETRY_AFTER_SECONDS
            ),
        ) from exc

    stored_image = image_storage_service.store(image)

    try:
        prediction = prediction_admission_service.admit_prediction(
            db,
            user_id=user_id,
            stored_image=stored_image,
        )
        db.commit()
    except PredictionUserOutstandingExceededError as exc:
        db.rollback()
        _delete_orphaned_image(stored_image.object_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many outstanding prediction jobs. Retry later.",
            headers=_retry_after_header(exc.retry_after_seconds),
        ) from exc
    except PredictionGlobalCapacityExceededError as exc:
        db.rollback()
        _delete_orphaned_image(stored_image.object_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction service is temporarily at capacity. Retry later.",
            headers=_retry_after_header(exc.retry_after_seconds),
        ) from exc
    except PredictionAdmissionUnavailableError as exc:
        db.rollback()
        _delete_orphaned_image(stored_image.object_key)
        logger.exception("prediction_queue_admission_unavailable user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction service is temporarily unavailable. Retry later.",
            headers=_retry_after_header(
                settings.PREDICTION_CAPACITY_RETRY_AFTER_SECONDS
            ),
        ) from exc
    except Exception:
        db.rollback()
        _delete_orphaned_image(stored_image.object_key)
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
