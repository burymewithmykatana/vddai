import os
import threading
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Prediction, PredictionStatus, User
from app.tests.test_prediction_worker_reliability import result_for
from app.workers.prediction_worker import (
    PredictionRetryPolicy,
    _claim_next_prediction,
    _persist_success,
    _recover_one_stale_prediction,
)

POSTGRES_TEST_URL = os.environ.get("VDDAI_TEST_POSTGRES_DATABASE_URL")

pytestmark = [
    pytest.mark.postgres_integration,
    pytest.mark.skipif(
        not POSTGRES_TEST_URL,
        reason="VDDAI_TEST_POSTGRES_DATABASE_URL is not configured.",
    ),
]


@pytest.fixture
def postgres_engine() -> Engine:
    assert POSTGRES_TEST_URL is not None
    schema_name = f"vddai_w7d2_{uuid4().hex}"
    administration_engine = sa.create_engine(POSTGRES_TEST_URL)
    with administration_engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema_name}"'))

    test_engine = sa.create_engine(
        POSTGRES_TEST_URL,
        connect_args={"options": f"-csearch_path={schema_name}"},
    )
    Base.metadata.create_all(bind=test_engine)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
        with administration_engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA "{schema_name}"'))
        administration_engine.dispose()


def create_postgres_prediction(
    session_factory: sessionmaker[Session],
    *,
    created_at: datetime,
) -> int:
    with session_factory() as db:
        user = User(
            email=f"postgres-{uuid4().hex}@example.com",
            hashed_password="not-a-real-password",
            is_active=True,
            is_admin=False,
        )
        db.add(user)
        db.flush()
        prediction = Prediction(
            user_id=user.id,
            image_object_key=f"predictions/{uuid4().hex}.png",
            image_format="PNG",
            image_width=16,
            image_height=16,
            status=PredictionStatus.QUEUED.value,
            created_at=created_at,
        )
        db.add(prediction)
        db.commit()
        return prediction.id


def test_postgres_skip_locked_prevents_concurrent_claim(
    postgres_engine: Engine,
) -> None:
    session_factory = sessionmaker(bind=postgres_engine)
    now = datetime(2026, 8, 20, 10, 0, 0)
    prediction_id = create_postgres_prediction(
        session_factory,
        created_at=now - timedelta(seconds=1),
    )
    policy = PredictionRetryPolicy(
        max_attempts=3,
        retry_delay_seconds=5,
        attempt_lease_seconds=60,
    )
    commit_entered = threading.Event()
    allow_commit = threading.Event()
    claimed: list[object] = []
    errors: list[BaseException] = []

    def claim_with_blocked_commit() -> None:
        try:
            with session_factory() as db:
                real_commit = db.commit

                def blocked_commit() -> None:
                    commit_entered.set()
                    if not allow_commit.wait(timeout=10):
                        raise TimeoutError("Timed out waiting to release claim commit.")
                    real_commit()

                db.commit = blocked_commit  # type: ignore[method-assign]
                claimed.append(_claim_next_prediction(db, now=now, retry_policy=policy))
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=claim_with_blocked_commit)
    worker.start()
    assert commit_entered.wait(timeout=10)
    try:
        with session_factory() as competing_db:
            competing_claim = _claim_next_prediction(
                competing_db,
                now=now,
                retry_policy=policy,
            )
            assert competing_claim is None
    finally:
        allow_commit.set()
        worker.join(timeout=10)

    assert not worker.is_alive()
    assert errors == []
    assert len(claimed) == 1
    assert claimed[0] is not None
    with session_factory() as inspection_db:
        prediction = inspection_db.get(Prediction, prediction_id)
        assert prediction is not None
        assert prediction.status == PredictionStatus.PROCESSING.value
        assert prediction.attempt_count == 1


def test_postgres_recovery_fences_expired_worker_result(
    postgres_engine: Engine,
) -> None:
    session_factory = sessionmaker(bind=postgres_engine)
    started_at = datetime(2026, 8, 20, 10, 0, 0)
    prediction_id = create_postgres_prediction(
        session_factory,
        created_at=started_at - timedelta(seconds=1),
    )
    policy = PredictionRetryPolicy(
        max_attempts=3,
        retry_delay_seconds=5,
        attempt_lease_seconds=10,
    )

    with session_factory() as original_db:
        original_claim = _claim_next_prediction(
            original_db,
            now=started_at,
            retry_policy=policy,
        )
        assert original_claim is not None

    with session_factory() as replacement_db:
        assert _recover_one_stale_prediction(
            replacement_db,
            now=started_at + timedelta(seconds=10),
            retry_policy=policy,
        )
        replacement_claim = _claim_next_prediction(
            replacement_db,
            now=started_at + timedelta(seconds=15),
            retry_policy=policy,
        )
        assert replacement_claim is not None
        assert replacement_claim.attempt == 2

    with session_factory() as stale_db:
        assert not _persist_success(
            stale_db,
            claim=original_claim,
            result=result_for("package-postgres-stale-v1"),
            retry_policy=policy,
            now=started_at + timedelta(seconds=16),
        )

    with session_factory() as replacement_db:
        assert _persist_success(
            replacement_db,
            claim=replacement_claim,
            result=result_for("package-postgres-current-v1"),
            retry_policy=policy,
            now=started_at + timedelta(seconds=16),
        )

    with session_factory() as stale_db:
        assert not _persist_success(
            stale_db,
            claim=original_claim,
            result=result_for("package-postgres-stale-v1"),
            retry_policy=policy,
            now=started_at + timedelta(seconds=17),
        )

    with session_factory() as inspection_db:
        completed = inspection_db.get(Prediction, prediction_id)
        assert completed is not None
        assert completed.status == PredictionStatus.COMPLETED.value
        assert completed.attempt_count == 2
        assert completed.model_version == "package-postgres-current-v1"
