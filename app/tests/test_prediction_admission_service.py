from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.models import (
    Prediction,
    PredictionAdmissionControl,
    PredictionStatus,
    User,
)
from app.services.image_storage_service import StoredImage
from app.services.prediction_admission_service import (
    PredictionAdmissionPolicy,
    PredictionAdmissionService,
    PredictionGlobalCapacityExceededError,
    PredictionRequestRateExceededError,
    PredictionUserOutstandingExceededError,
)


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(PredictionAdmissionControl.__table__.insert().values(id=1))
    factory = sessionmaker(bind=engine)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_user(db: Session, email: str) -> User:
    user = User(
        email=email,
        hashed_password="not-a-real-password",
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _stored_image(suffix: str = "one") -> StoredImage:
    return StoredImage(
        object_key=f"predictions/{suffix}.png",
        format="PNG",
        width=16,
        height=16,
    )


def _policy(**overrides: int) -> PredictionAdmissionPolicy:
    values = {
        "rate_limit_requests": 2,
        "rate_limit_window_seconds": 60,
        "user_outstanding_limit": 2,
        "global_outstanding_limit": 4,
        "capacity_retry_after_seconds": 5,
    }
    values.update(overrides)
    return PredictionAdmissionPolicy(**values)


def test_rate_window_enforces_boundary_and_resets(
    session_factory: sessionmaker[Session],
) -> None:
    service = PredictionAdmissionService()
    started_at = datetime(2026, 8, 21, 12, 0, 0)
    with session_factory() as db:
        user = _create_user(db, "rate@example.com")
        service.consume_request_slot(
            db, user_id=user.id, now=started_at, policy=_policy()
        )
        db.commit()
        service.consume_request_slot(
            db,
            user_id=user.id,
            now=started_at + timedelta(seconds=1),
            policy=_policy(),
        )
        db.commit()

        with pytest.raises(PredictionRequestRateExceededError) as exc_info:
            service.consume_request_slot(
                db,
                user_id=user.id,
                now=started_at + timedelta(seconds=2),
                policy=_policy(),
            )
        db.rollback()
        assert exc_info.value.retry_after_seconds == 58

        service.consume_request_slot(
            db,
            user_id=user.id,
            now=started_at + timedelta(seconds=60),
            policy=_policy(),
        )
        db.commit()


@pytest.mark.parametrize(
    ("status", "counts_as_outstanding"),
    [
        (PredictionStatus.QUEUED.value, True),
        (PredictionStatus.PROCESSING.value, True),
        (PredictionStatus.COMPLETED.value, False),
        (PredictionStatus.FAILED.value, False),
        (PredictionStatus.NEEDS_REVIEW.value, False),
    ],
)
def test_only_queued_and_processing_count_as_outstanding(
    session_factory: sessionmaker[Session],
    status: str,
    counts_as_outstanding: bool,
) -> None:
    service = PredictionAdmissionService()
    with session_factory() as db:
        user = _create_user(db, f"{status}@example.com")
        db.add(
            Prediction(
                user_id=user.id,
                image_object_key=f"predictions/{status}.png",
                image_format="PNG",
                image_width=16,
                image_height=16,
                status=status,
            )
        )
        db.commit()

        if counts_as_outstanding:
            with pytest.raises(PredictionUserOutstandingExceededError):
                service.admit_prediction(
                    db,
                    user_id=user.id,
                    stored_image=_stored_image("new"),
                    policy=_policy(
                        user_outstanding_limit=1,
                        global_outstanding_limit=2,
                    ),
                )
        else:
            admitted = service.admit_prediction(
                db,
                user_id=user.id,
                stored_image=_stored_image("new"),
                policy=_policy(
                    user_outstanding_limit=1,
                    global_outstanding_limit=2,
                ),
            )
            assert admitted.status == PredictionStatus.QUEUED.value


def test_global_capacity_applies_across_users(
    session_factory: sessionmaker[Session],
) -> None:
    service = PredictionAdmissionService()
    with session_factory() as db:
        first = _create_user(db, "first-global@example.com")
        second = _create_user(db, "second-global@example.com")
        db.add(
            Prediction(
                user_id=first.id,
                image_object_key="predictions/existing.png",
                image_format="PNG",
                image_width=16,
                image_height=16,
                status=PredictionStatus.QUEUED.value,
            )
        )
        db.commit()

        with pytest.raises(PredictionGlobalCapacityExceededError) as exc_info:
            service.admit_prediction(
                db,
                user_id=second.id,
                stored_image=_stored_image("second"),
                policy=_policy(
                    user_outstanding_limit=1,
                    global_outstanding_limit=1,
                ),
            )

        assert exc_info.value.retry_after_seconds == 5


def test_settings_define_defaults_and_reject_invalid_guardrails() -> None:
    configured = Settings(_env_file=None)

    assert configured.MAX_IMAGE_SIZE_MB == 5
    assert configured.PREDICTION_RATE_LIMIT_REQUESTS == 10
    assert configured.PREDICTION_RATE_LIMIT_WINDOW_SECONDS == 60
    assert configured.PREDICTION_USER_OUTSTANDING_LIMIT == 5
    assert configured.PREDICTION_GLOBAL_OUTSTANDING_LIMIT == 50
    assert configured.PREDICTION_CAPACITY_RETRY_AFTER_SECONDS == 5

    for field_name in (
        "MAX_IMAGE_SIZE_MB",
        "PREDICTION_RATE_LIMIT_REQUESTS",
        "PREDICTION_RATE_LIMIT_WINDOW_SECONDS",
        "PREDICTION_USER_OUTSTANDING_LIMIT",
        "PREDICTION_GLOBAL_OUTSTANDING_LIMIT",
        "PREDICTION_CAPACITY_RETRY_AFTER_SECONDS",
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{field_name: 0})

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            PREDICTION_USER_OUTSTANDING_LIMIT=6,
            PREDICTION_GLOBAL_OUTSTANDING_LIMIT=5,
        )
