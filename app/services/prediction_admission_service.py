from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.prediction import Prediction, PredictionStatus
from app.models.prediction_admission import (
    PredictionAdmissionControl,
    PredictionRequestRateWindow,
)
from app.models.user import User
from app.services.image_storage_service import StoredImage


class PredictionAdmissionUnavailableError(RuntimeError):
    """Raised when admission state is missing or cannot safely be used."""


class PredictionAdmissionLimitError(RuntimeError):
    def __init__(self, *, retry_after_seconds: int) -> None:
        super().__init__()
        self.retry_after_seconds = retry_after_seconds


class PredictionRequestRateExceededError(PredictionAdmissionLimitError):
    """Raised when an authenticated user has exhausted the request window."""


class PredictionUserOutstandingExceededError(PredictionAdmissionLimitError):
    """Raised when a user already owns the configured outstanding maximum."""


class PredictionGlobalCapacityExceededError(PredictionAdmissionLimitError):
    """Raised when the service-wide outstanding maximum has been reached."""


@dataclass(frozen=True)
class PredictionAdmissionPolicy:
    rate_limit_requests: int
    rate_limit_window_seconds: int
    user_outstanding_limit: int
    global_outstanding_limit: int
    capacity_retry_after_seconds: int

    def __post_init__(self) -> None:
        values = (
            self.rate_limit_requests,
            self.rate_limit_window_seconds,
            self.user_outstanding_limit,
            self.global_outstanding_limit,
            self.capacity_retry_after_seconds,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in values
        ):
            raise ValueError("Prediction admission limits must be positive integers.")
        if self.global_outstanding_limit < self.user_outstanding_limit:
            raise ValueError(
                "Global prediction capacity cannot be below the per-user limit."
            )


def _configured_policy() -> PredictionAdmissionPolicy:
    return PredictionAdmissionPolicy(
        rate_limit_requests=settings.PREDICTION_RATE_LIMIT_REQUESTS,
        rate_limit_window_seconds=settings.PREDICTION_RATE_LIMIT_WINDOW_SECONDS,
        user_outstanding_limit=settings.PREDICTION_USER_OUTSTANDING_LIMIT,
        global_outstanding_limit=settings.PREDICTION_GLOBAL_OUTSTANDING_LIMIT,
        capacity_retry_after_seconds=(settings.PREDICTION_CAPACITY_RETRY_AFTER_SECONDS),
    )


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PredictionAdmissionService:
    """Coordinate authenticated rate state and atomic prediction admission."""

    def consume_request_slot(
        self,
        db: Session,
        *,
        user_id: int,
        now: datetime | None = None,
        policy: PredictionAdmissionPolicy | None = None,
    ) -> None:
        effective_policy = policy or _configured_policy()
        effective_now = now or _utc_now_naive()
        if effective_now.tzinfo is not None:
            raise ValueError(
                "Prediction admission timestamps must be timezone-naive UTC."
            )

        locked_user_id = db.scalar(
            select(User.id).where(User.id == user_id).with_for_update()
        )
        if locked_user_id is None:
            raise PredictionAdmissionUnavailableError(
                "Authenticated admission user no longer exists."
            )

        rate_window = db.get(PredictionRequestRateWindow, user_id)
        if rate_window is None:
            db.add(
                PredictionRequestRateWindow(
                    user_id=user_id,
                    window_started_at=effective_now,
                    request_count=1,
                )
            )
            return

        window_ends_at = rate_window.window_started_at + timedelta(
            seconds=effective_policy.rate_limit_window_seconds
        )
        if effective_now >= window_ends_at:
            rate_window.window_started_at = effective_now
            rate_window.request_count = 1
            return

        if rate_window.request_count >= effective_policy.rate_limit_requests:
            retry_after = max(
                1,
                math.ceil((window_ends_at - effective_now).total_seconds()),
            )
            raise PredictionRequestRateExceededError(retry_after_seconds=retry_after)

        rate_window.request_count += 1

    def admit_prediction(
        self,
        db: Session,
        *,
        user_id: int,
        stored_image: StoredImage,
        policy: PredictionAdmissionPolicy | None = None,
    ) -> Prediction:
        effective_policy = policy or _configured_policy()
        admission_control = db.scalar(
            select(PredictionAdmissionControl)
            .where(PredictionAdmissionControl.id == 1)
            .with_for_update()
        )
        if admission_control is None:
            raise PredictionAdmissionUnavailableError(
                "Prediction admission control row is missing."
            )

        outstanding_statuses = (
            PredictionStatus.QUEUED.value,
            PredictionStatus.PROCESSING.value,
        )
        user_outstanding = db.scalar(
            select(func.count(Prediction.id)).where(
                Prediction.user_id == user_id,
                Prediction.status.in_(outstanding_statuses),
            )
        )
        if (user_outstanding or 0) >= effective_policy.user_outstanding_limit:
            raise PredictionUserOutstandingExceededError(
                retry_after_seconds=effective_policy.capacity_retry_after_seconds
            )

        global_outstanding = db.scalar(
            select(func.count(Prediction.id)).where(
                Prediction.status.in_(outstanding_statuses)
            )
        )
        if (global_outstanding or 0) >= effective_policy.global_outstanding_limit:
            raise PredictionGlobalCapacityExceededError(
                retry_after_seconds=effective_policy.capacity_retry_after_seconds
            )

        prediction = Prediction(
            user_id=user_id,
            image_object_key=stored_image.object_key,
            image_format=stored_image.format,
            image_width=stored_image.width,
            image_height=stored_image.height,
            status=PredictionStatus.QUEUED.value,
        )
        db.add(prediction)
        return prediction


prediction_admission_service = PredictionAdmissionService()
