import os
import threading
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes.auth import register_user
from app.db.base import Base
from app.models import Prediction, PredictionAdmissionControl, User
from app.schemas.user import UserCreate
from app.services.image_storage_service import StoredImage
from app.services.prediction_admission_service import (
    PredictionAdmissionPolicy,
    PredictionAdmissionService,
    PredictionGlobalCapacityExceededError,
    PredictionRequestRateExceededError,
    PredictionUserOutstandingExceededError,
)

POSTGRES_TEST_URL = os.environ.get("VDDAI_TEST_POSTGRES_DATABASE_URL")

pytestmark = [
    pytest.mark.w7_production_gate,
    pytest.mark.postgres_integration,
    pytest.mark.skipif(
        not POSTGRES_TEST_URL,
        reason="VDDAI_TEST_POSTGRES_DATABASE_URL is not configured.",
    ),
]


@pytest.fixture
def postgres_engine() -> Engine:
    assert POSTGRES_TEST_URL is not None
    schema_name = f"vddai_w7d3_{uuid4().hex}"
    administration_engine = sa.create_engine(POSTGRES_TEST_URL)
    with administration_engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema_name}"'))

    test_engine = sa.create_engine(
        POSTGRES_TEST_URL,
        connect_args={"options": f"-csearch_path={schema_name}"},
    )
    Base.metadata.create_all(bind=test_engine)
    with test_engine.begin() as connection:
        connection.execute(PredictionAdmissionControl.__table__.insert().values(id=1))
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
        with administration_engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA "{schema_name}"'))
        administration_engine.dispose()


def _create_users(
    session_factory: sessionmaker[Session],
    count: int,
) -> list[int]:
    with session_factory() as db:
        users = [
            User(
                email=f"postgres-admission-{uuid4().hex}@example.com",
                hashed_password="not-a-real-password",
                is_active=True,
                is_admin=False,
            )
            for _ in range(count)
        ]
        db.add_all(users)
        db.commit()
        return [user.id for user in users]


def _policy(*, user_limit: int, global_limit: int) -> PredictionAdmissionPolicy:
    return PredictionAdmissionPolicy(
        rate_limit_requests=1,
        rate_limit_window_seconds=60,
        user_outstanding_limit=user_limit,
        global_outstanding_limit=global_limit,
        capacity_retry_after_seconds=5,
    )


def test_postgres_duplicate_registration_race_returns_one_created_and_one_conflict(
    postgres_engine: Engine,
) -> None:
    session_factory = sessionmaker(bind=postgres_engine)
    first_lookup_barrier = threading.Barrier(2)
    outcomes: list[int] = []
    errors: list[BaseException] = []
    credentials = UserCreate(
        email="postgres-registration-race@example.com",
        password="registration-race-password",
    )

    def register() -> None:
        try:
            with session_factory() as db:
                real_scalar = db.scalar
                first_lookup = True

                def synchronized_scalar(*args: object, **kwargs: object):
                    nonlocal first_lookup
                    result = real_scalar(*args, **kwargs)
                    if first_lookup:
                        first_lookup = False
                        first_lookup_barrier.wait(timeout=10)
                    return result

                db.scalar = synchronized_scalar  # type: ignore[method-assign]
                try:
                    register_user(credentials, db)
                    outcomes.append(201)
                except HTTPException as exc:
                    outcomes.append(exc.status_code)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=register) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(outcomes) == [201, 409]
    with session_factory() as db:
        assert db.query(User).filter(User.email == credentials.email).count() == 1


def test_postgres_user_lock_prevents_concurrent_rate_window_overshoot(
    postgres_engine: Engine,
) -> None:
    session_factory = sessionmaker(bind=postgres_engine)
    user_id = _create_users(session_factory, 1)[0]
    service = PredictionAdmissionService()
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    errors: list[BaseException] = []

    def consume() -> None:
        try:
            with session_factory() as db:
                barrier.wait(timeout=10)
                try:
                    service.consume_request_slot(
                        db,
                        user_id=user_id,
                        policy=_policy(user_limit=1, global_limit=2),
                    )
                    db.commit()
                    outcomes.append("accepted")
                except PredictionRequestRateExceededError:
                    db.rollback()
                    outcomes.append("limited")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(outcomes) == ["accepted", "limited"]


def test_postgres_singleton_lock_prevents_per_user_admission_overshoot(
    postgres_engine: Engine,
) -> None:
    session_factory = sessionmaker(bind=postgres_engine)
    user_id = _create_users(session_factory, 1)[0]
    service = PredictionAdmissionService()
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    errors: list[BaseException] = []

    def admit(suffix: str) -> None:
        try:
            with session_factory() as db:
                barrier.wait(timeout=10)
                try:
                    service.admit_prediction(
                        db,
                        user_id=user_id,
                        stored_image=StoredImage(
                            object_key=f"predictions/{suffix}.png",
                            format="PNG",
                            width=16,
                            height=16,
                        ),
                        policy=_policy(user_limit=1, global_limit=2),
                    )
                    db.commit()
                    outcomes.append("accepted")
                except PredictionUserOutstandingExceededError:
                    db.rollback()
                    outcomes.append("limited")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=admit, args=(str(index),)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(outcomes) == ["accepted", "limited"]
    with session_factory() as db:
        assert db.query(Prediction).count() == 1


def test_postgres_singleton_lock_prevents_global_admission_overshoot(
    postgres_engine: Engine,
) -> None:
    session_factory = sessionmaker(bind=postgres_engine)
    user_ids = _create_users(session_factory, 2)
    service = PredictionAdmissionService()
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    errors: list[BaseException] = []

    def admit(user_id: int) -> None:
        try:
            with session_factory() as db:
                barrier.wait(timeout=10)
                try:
                    service.admit_prediction(
                        db,
                        user_id=user_id,
                        stored_image=StoredImage(
                            object_key=f"predictions/{user_id}.png",
                            format="PNG",
                            width=16,
                            height=16,
                        ),
                        policy=_policy(user_limit=1, global_limit=1),
                    )
                    db.commit()
                    outcomes.append("accepted")
                except PredictionGlobalCapacityExceededError:
                    db.rollback()
                    outcomes.append("limited")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=admit, args=(user_id,)) for user_id in user_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(outcomes) == ["accepted", "limited"]
    with session_factory() as db:
        assert db.query(Prediction).count() == 1
