from functools import partial
from time import perf_counter_ns

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.logging import LogError, LogEvent, elapsed_ms, log_event
from app.models.prediction import Prediction, PredictionStatus
from app.models.user import User
from app.schemas import PredictionQueuedResponse, PredictionRead
from app.services.image_storage_service import StoredImage, image_storage_service
from app.services.prediction_admission_service import (
    PredictionAdmissionUnavailableError,
    PredictionGlobalCapacityExceededError,
    PredictionRequestRateExceededError,
    PredictionUserOutstandingExceededError,
    prediction_admission_service,
)

_log = partial(log_event, service="api")

router = APIRouter(prefix="/predictions", tags=["predictions"])


def _retry_after_header(seconds: int) -> dict[str, str]:
    return {"Retry-After": str(seconds)}


def _delete_orphaned_image(object_key: str) -> None:
    started_ns = perf_counter_ns()
    try:
        image_storage_service.delete(object_key)
    except Exception:
        _log(
            LogEvent.STORAGE_CLEANUP,
            status="error",
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.STORAGE_CLEANUP_FAILED,
        )
    else:
        _log(LogEvent.STORAGE_CLEANUP, status="ok", latency_ms=elapsed_ms(started_ns))


def _store_prediction_image(image: UploadFile) -> StoredImage:
    started_ns = perf_counter_ns()
    try:
        stored_image = image_storage_service.store(image)
    except HTTPException as exc:
        rejected = exc.status_code < 500
        _log(
            LogEvent.STORAGE_WRITE,
            status="rejected" if rejected else "error",
            latency_ms=elapsed_ms(started_ns),
            error_code=(
                LogError.UPLOAD_REJECTED if rejected else LogError.STORAGE_WRITE_FAILED
            ),
        )
        raise
    except Exception:
        _log(
            LogEvent.STORAGE_WRITE,
            status="error",
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.STORAGE_WRITE_FAILED,
        )
        raise
    _log(LogEvent.STORAGE_WRITE, status="ok", latency_ms=elapsed_ms(started_ns))
    return stored_image


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
    started_ns = perf_counter_ns()
    try:
        prediction_admission_service.consume_request_slot(
            db,
            user_id=user_id,
        )
        db.commit()
    except PredictionRequestRateExceededError as exc:
        db.rollback()
        _log(
            LogEvent.ENQUEUE,
            status="rejected",
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.RATE_LIMITED,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Prediction request rate limit exceeded. Retry later.",
            headers=_retry_after_header(exc.retry_after_seconds),
        ) from exc
    except PredictionAdmissionUnavailableError as exc:
        db.rollback()
        _log(
            LogEvent.ENQUEUE,
            status="error",
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.ADMISSION_UNAVAILABLE,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction service is temporarily unavailable. Retry later.",
            headers=_retry_after_header(
                settings.PREDICTION_CAPACITY_RETRY_AFTER_SECONDS
            ),
        ) from exc

    stored_image = _store_prediction_image(image)

    started_ns = perf_counter_ns()
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
        _log(
            LogEvent.ENQUEUE,
            status="rejected",
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.USER_CAPACITY,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many outstanding prediction jobs. Retry later.",
            headers=_retry_after_header(exc.retry_after_seconds),
        ) from exc
    except PredictionGlobalCapacityExceededError as exc:
        db.rollback()
        _delete_orphaned_image(stored_image.object_key)
        _log(
            LogEvent.ENQUEUE,
            status="rejected",
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.GLOBAL_CAPACITY,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction service is temporarily at capacity. Retry later.",
            headers=_retry_after_header(exc.retry_after_seconds),
        ) from exc
    except PredictionAdmissionUnavailableError as exc:
        db.rollback()
        _delete_orphaned_image(stored_image.object_key)
        _log(
            LogEvent.ENQUEUE,
            status="error",
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.ADMISSION_UNAVAILABLE,
        )
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
        _log(
            LogEvent.ENQUEUE,
            status="error",
            latency_ms=elapsed_ms(started_ns),
            error_code=LogError.ENQUEUE_FAILED,
        )
        raise

    identity = inspect(prediction).identity
    _log(
        LogEvent.ENQUEUE,
        status=PredictionStatus.QUEUED.value,
        prediction_id=identity[0] if identity else None,
        latency_ms=elapsed_ms(started_ns),
    )
    db.refresh(prediction)

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
    started_ns = perf_counter_ns()
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

    _log(
        LogEvent.READBACK,
        status=prediction.status,
        prediction_id=prediction.id,
        model_version=prediction.model_version,
        latency_ms=elapsed_ms(started_ns),
    )
    return prediction
