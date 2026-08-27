from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contracts.inference import AnomalyInferenceResult, PredictionLabel
from app.core.config import Settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.prediction import Prediction, PredictionStatus
from app.services.image_storage_service import ImageStorageError
from app.services.image_preprocessing_service import ImagePreprocessingService
from app.tests.image_fixtures import png_with_declared_dimensions
from app.tests.test_prediction_api import create_model_lineage
from app.workers import prediction_worker
from app.workers.prediction_worker import (
    PredictionRetryPolicy,
    _claim_next_prediction,
    _persist_success,
    _recover_one_stale_prediction,
    process_next_prediction,
)

pytestmark = pytest.mark.w7_production_gate


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def create_prediction(db: Session, *, created_at: datetime) -> Prediction:
    prediction = Prediction(
        user_id=1,
        image_object_key="predictions/reliability.png",
        image_format="PNG",
        image_width=16,
        image_height=16,
        status=PredictionStatus.QUEUED.value,
        created_at=created_at,
    )
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    return prediction


def result_for(package_id: str, *, score: float = 1.0) -> AnomalyInferenceResult:
    threshold = 2.0
    lineage = create_model_lineage(package_id=package_id, threshold=threshold)
    return AnomalyInferenceResult(
        predicted_label=PredictionLabel.NORMAL,
        anomaly_score=score,
        threshold=threshold,
        model_version=package_id,
        model_lineage=lineage,
        latency_ms=4,
    )


class MutableStorage:
    def __init__(
        self,
        error: Exception | None = None,
        contents: bytes = b"stored-image",
    ) -> None:
        self.error = error
        self.contents = contents
        self.read_count = 0

    def read(self, object_key: str) -> bytes:
        self.read_count += 1
        if self.error is not None:
            raise self.error
        return self.contents


class DeterministicInferenceService:
    def __init__(self, result: AnomalyInferenceResult) -> None:
        self.result = result
        self.predict_count = 0

    def predict(self, image_contents: bytes) -> AnomalyInferenceResult:
        assert image_contents == b"stored-image"
        self.predict_count += 1
        return self.result


class PreprocessingOnlyInferenceService:
    def __init__(self, *, max_input_pixels: int) -> None:
        self.preprocessing_service = ImagePreprocessingService(
            max_input_pixels=max_input_pixels
        )
        self.predict_count = 0

    def predict(self, image_contents: bytes) -> AnomalyInferenceResult:
        self.predict_count += 1
        self.preprocessing_service.preprocess_bytes(image_contents)
        raise AssertionError("Over-limit legacy input unexpectedly reached inference.")


def test_prediction_retry_substate_preserves_public_processing_lifecycle() -> None:
    created_at = datetime(2026, 8, 20, 10, 0, 0)
    prediction = Prediction(
        user_id=1,
        image_object_key="predictions/internal.png",
        image_format="PNG",
        image_width=16,
        image_height=16,
        status=PredictionStatus.QUEUED.value,
        created_at=created_at,
        attempt_count=0,
    )
    first_attempt = prediction.start_processing(
        at=created_at + timedelta(seconds=1),
        lease_expires_at=created_at + timedelta(minutes=5),
    )
    prediction.schedule_retry(
        expected_attempt=first_attempt,
        error_message="ImageStorageError: temporarily unreadable",
        next_attempt_at=created_at + timedelta(seconds=10),
    )

    assert prediction.status == PredictionStatus.PROCESSING.value
    assert prediction.processing_started_at == created_at + timedelta(seconds=1)
    assert prediction.attempt_count == 1
    assert prediction.lease_expires_at is None
    assert prediction.next_attempt_at == created_at + timedelta(seconds=10)
    assert prediction.completed_at is None
    assert prediction.failure_code is None

    with pytest.raises(ValueError, match="not eligible"):
        prediction.start_processing(
            at=created_at + timedelta(seconds=9),
            lease_expires_at=created_at + timedelta(minutes=5),
        )

    second_attempt = prediction.start_processing(
        at=created_at + timedelta(seconds=10),
        lease_expires_at=created_at + timedelta(minutes=6),
    )
    assert second_attempt == 2
    assert prediction.processing_started_at == created_at + timedelta(seconds=1)
    assert prediction.next_attempt_at is None
    assert prediction.error_message is None


def test_prediction_rejects_stale_attempt_token() -> None:
    created_at = datetime(2026, 8, 20, 10, 0, 0)
    prediction = Prediction(
        user_id=1,
        image_object_key="predictions/internal.png",
        image_format="PNG",
        image_width=16,
        image_height=16,
        status=PredictionStatus.QUEUED.value,
        created_at=created_at,
        attempt_count=0,
    )
    attempt = prediction.start_processing(
        at=created_at,
        lease_expires_at=created_at + timedelta(minutes=5),
    )

    with pytest.raises(ValueError, match="token is stale"):
        prediction.complete(
            result_for("package-stale-v1"),
            expected_attempt=attempt + 1,
            at=created_at + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="token is stale"):
        prediction.fail(
            expected_attempt=attempt + 1,
            error_message="RuntimeError: stale",
            at=created_at + timedelta(seconds=1),
        )


def test_retryable_storage_failure_retries_and_completes(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_time = [datetime(2026, 8, 20, 10, 0, 0)]
    monkeypatch.setattr(
        prediction_worker,
        "_utc_now_naive",
        lambda: current_time[0],
    )
    policy = PredictionRetryPolicy(
        max_attempts=3,
        retry_delay_seconds=5,
        attempt_lease_seconds=60,
    )
    prediction = create_prediction(
        db,
        created_at=current_time[0] - timedelta(seconds=1),
    )
    storage = MutableStorage(ImageStorageError("temporarily unreadable"))
    inference = DeterministicInferenceService(result_for("package-retry-v1"))

    assert (
        process_next_prediction(
            db,
            inference_service=inference,
            storage_service=storage,
            retry_policy=policy,
        )
        is False
    )
    db.expire_all()
    retry_waiting = db.get(Prediction, prediction.id)
    assert retry_waiting is not None
    assert retry_waiting.status == PredictionStatus.PROCESSING.value
    assert retry_waiting.attempt_count == 1
    assert retry_waiting.lease_expires_at is None
    assert retry_waiting.next_attempt_at == current_time[0] + timedelta(seconds=5)
    assert retry_waiting.error_message.startswith("ImageStorageError:")

    assert (
        process_next_prediction(
            db,
            inference_service=inference,
            storage_service=storage,
            retry_policy=policy,
        )
        is False
    )
    assert storage.read_count == 1

    storage.error = None
    current_time[0] += timedelta(seconds=5)
    assert (
        process_next_prediction(
            db,
            inference_service=inference,
            storage_service=storage,
            retry_policy=policy,
        )
        is True
    )
    db.expire_all()
    completed = db.get(Prediction, prediction.id)
    assert completed is not None
    assert completed.status == PredictionStatus.COMPLETED.value
    assert completed.attempt_count == 2
    assert completed.lease_expires_at is None
    assert completed.next_attempt_at is None
    assert completed.error_message is None


def test_retry_exhaustion_becomes_terminal_failure(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_time = [datetime(2026, 8, 20, 10, 0, 0)]
    monkeypatch.setattr(
        prediction_worker,
        "_utc_now_naive",
        lambda: current_time[0],
    )
    policy = PredictionRetryPolicy(
        max_attempts=2,
        retry_delay_seconds=5,
        attempt_lease_seconds=60,
    )
    prediction = create_prediction(
        db,
        created_at=current_time[0] - timedelta(seconds=1),
    )
    storage = MutableStorage(ImageStorageError("still unreadable"))
    inference = DeterministicInferenceService(result_for("package-exhaust-v1"))

    assert not process_next_prediction(db, inference, storage, policy)
    current_time[0] += timedelta(seconds=5)
    assert not process_next_prediction(db, inference, storage, policy)

    db.expire_all()
    failed = db.get(Prediction, prediction.id)
    assert failed is not None
    assert failed.status == PredictionStatus.FAILED.value
    assert failed.attempt_count == 2
    assert failed.failure_code == "inference_failed"
    assert failed.error_message.startswith("RetryExhausted after 2 attempts:")
    assert failed.lease_expires_at is None
    assert failed.next_attempt_at is None


def test_legacy_over_limit_stored_image_fails_safely_without_retry(
    db: Session,
) -> None:
    prediction = create_prediction(
        db,
        created_at=datetime(2026, 8, 20, 10, 0, 0),
    )
    inference = PreprocessingOnlyInferenceService(max_input_pixels=16)
    storage = MutableStorage(contents=png_with_declared_dimensions(width=17, height=1))

    assert not process_next_prediction(
        db,
        inference_service=inference,
        storage_service=storage,
        retry_policy=PredictionRetryPolicy(3, 5, 60),
    )

    db.expire_all()
    failed = db.get(Prediction, prediction.id)
    assert failed is not None
    assert failed.status == PredictionStatus.FAILED.value
    assert failed.failure_code == "inference_failed"
    assert failed.attempt_count == 1
    assert failed.error_message.startswith("ImagePreprocessingError:")
    assert inference.predict_count == 1


def test_lowered_retry_limit_fails_due_retry_without_another_attempt(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_time = [datetime(2026, 8, 20, 10, 0, 0)]
    monkeypatch.setattr(
        prediction_worker,
        "_utc_now_naive",
        lambda: current_time[0],
    )
    prediction = create_prediction(
        db,
        created_at=current_time[0] - timedelta(seconds=1),
    )
    storage = MutableStorage(ImageStorageError("temporarily unreadable"))
    inference = DeterministicInferenceService(result_for("package-lowered-v1"))

    assert not process_next_prediction(
        db,
        inference_service=inference,
        storage_service=storage,
        retry_policy=PredictionRetryPolicy(3, 5, 60),
    )
    current_time[0] += timedelta(seconds=5)
    storage.error = None

    assert not process_next_prediction(
        db,
        inference_service=inference,
        storage_service=storage,
        retry_policy=PredictionRetryPolicy(1, 5, 60),
    )

    db.expire_all()
    failed = db.get(Prediction, prediction.id)
    assert failed is not None
    assert failed.status == PredictionStatus.FAILED.value
    assert failed.attempt_count == 1
    assert failed.failure_code == "inference_failed"
    assert failed.error_message == (
        "RetryExhausted after 1 attempts: configured maximum is 1."
    )
    assert failed.completed_at == current_time[0]
    assert failed.lease_expires_at is None
    assert failed.next_attempt_at is None
    assert storage.read_count == 1
    assert inference.predict_count == 0


def test_expired_final_attempt_is_recovered_to_terminal_failure(db: Session) -> None:
    policy = PredictionRetryPolicy(
        max_attempts=3,
        retry_delay_seconds=5,
        attempt_lease_seconds=10,
    )
    started_at = datetime(2026, 8, 20, 10, 0, 0)
    prediction = Prediction(
        user_id=1,
        image_object_key="predictions/expired.png",
        image_format="PNG",
        image_width=16,
        image_height=16,
        status=PredictionStatus.PROCESSING.value,
        created_at=started_at - timedelta(seconds=1),
        processing_started_at=started_at,
        attempt_count=3,
        lease_expires_at=started_at + timedelta(seconds=10),
    )
    db.add(prediction)
    db.commit()

    assert _recover_one_stale_prediction(
        db,
        now=started_at + timedelta(seconds=10),
        retry_policy=policy,
    )
    db.expire_all()
    failed = db.get(Prediction, prediction.id)
    assert failed is not None
    assert failed.status == PredictionStatus.FAILED.value
    assert failed.error_message.startswith("RetryExhausted after 3 attempts:")
    assert failed.completed_at == started_at + timedelta(seconds=10)


def test_claim_commit_failure_leaves_job_queued_without_consuming_attempt(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 20, 10, 0, 0)
    prediction = create_prediction(db, created_at=now - timedelta(seconds=1))
    real_commit = db.commit

    def fail_claim_commit() -> None:
        raise SQLAlchemyError("simulated claim commit failure")

    monkeypatch.setattr(db, "commit", fail_claim_commit)
    claim = _claim_next_prediction(
        db,
        now=now,
        retry_policy=PredictionRetryPolicy(3, 5, 60),
    )
    monkeypatch.setattr(db, "commit", real_commit)

    assert claim is None
    db.expire_all()
    queued = db.get(Prediction, prediction.id)
    assert queued is not None
    assert queued.status == PredictionStatus.QUEUED.value
    assert queued.attempt_count == 0
    assert queued.processing_started_at is None
    assert queued.lease_expires_at is None


def test_ambiguous_result_commit_detects_already_completed_row(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 20, 10, 0, 0)
    prediction = create_prediction(db, created_at=now - timedelta(seconds=1))
    real_commit = db.commit
    commit_calls = 0

    def commit_then_report_connection_error() -> None:
        nonlocal commit_calls
        commit_calls += 1
        real_commit()
        if commit_calls == 2:
            raise SQLAlchemyError("connection lost after server commit")

    monkeypatch.setattr(db, "commit", commit_then_report_connection_error)
    completed = process_next_prediction(
        db,
        inference_service=DeterministicInferenceService(
            result_for("package-ambiguous-v1")
        ),
        storage_service=MutableStorage(),
        retry_policy=PredictionRetryPolicy(3, 5, 60),
    )
    monkeypatch.setattr(db, "commit", real_commit)

    assert completed is True
    db.expire_all()
    persisted = db.get(Prediction, prediction.id)
    assert persisted is not None
    assert persisted.status == PredictionStatus.COMPLETED.value
    assert persisted.attempt_count == 1
    assert persisted.model_version == "package-ambiguous-v1"


def test_worker_restart_recovers_expired_attempt(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_time = [datetime(2026, 8, 20, 10, 0, 0)]
    monkeypatch.setattr(
        prediction_worker,
        "_utc_now_naive",
        lambda: current_time[0],
    )
    policy = PredictionRetryPolicy(
        max_attempts=3,
        retry_delay_seconds=5,
        attempt_lease_seconds=10,
    )
    prediction = create_prediction(
        db,
        created_at=current_time[0] - timedelta(seconds=1),
    )
    prediction_id = prediction.id

    class InterruptedInferenceService:
        def predict(self, image_contents: bytes) -> AnomalyInferenceResult:
            raise KeyboardInterrupt("simulated worker interruption")

    with pytest.raises(KeyboardInterrupt, match="worker interruption"):
        process_next_prediction(
            db,
            inference_service=InterruptedInferenceService(),
            storage_service=MutableStorage(),
            retry_policy=policy,
        )
    db.close()

    restart_db = SessionLocal()
    try:
        current_time[0] += timedelta(seconds=10)
        inference = DeterministicInferenceService(result_for("package-restart-v1"))
        assert not process_next_prediction(
            restart_db,
            inference_service=inference,
            storage_service=MutableStorage(),
            retry_policy=policy,
        )
        current_time[0] += timedelta(seconds=5)
        assert process_next_prediction(
            restart_db,
            inference_service=inference,
            storage_service=MutableStorage(),
            retry_policy=policy,
        )
        restart_db.expire_all()
        completed = restart_db.get(Prediction, prediction_id)
        assert completed is not None
        assert completed.status == PredictionStatus.COMPLETED.value
        assert completed.attempt_count == 2
    finally:
        restart_db.close()


def test_interruption_after_inference_before_settlement_is_recoverable(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_time = datetime(2026, 8, 20, 10, 0, 0)
    monkeypatch.setattr(
        prediction_worker,
        "_utc_now_naive",
        lambda: current_time,
    )
    policy = PredictionRetryPolicy(3, 5, 10)
    prediction = create_prediction(
        db,
        created_at=current_time - timedelta(seconds=1),
    )
    prediction_id = prediction.id
    inference = DeterministicInferenceService(result_for("package-interrupted-v1"))

    def interrupt_before_settlement(*args: object, **kwargs: object) -> bool:
        raise KeyboardInterrupt("interrupted before terminal persistence")

    monkeypatch.setattr(
        prediction_worker,
        "_persist_success",
        interrupt_before_settlement,
    )
    with pytest.raises(KeyboardInterrupt, match="terminal persistence"):
        process_next_prediction(
            db,
            inference_service=inference,
            storage_service=MutableStorage(),
            retry_policy=policy,
        )
    assert inference.predict_count == 1
    db.expire_all()
    active = db.get(Prediction, prediction_id)
    assert active is not None
    assert active.status == PredictionStatus.PROCESSING.value
    assert active.attempt_count == 1
    assert active.lease_expires_at == current_time + timedelta(seconds=10)

    restart_db = SessionLocal()
    try:
        assert _recover_one_stale_prediction(
            restart_db,
            now=current_time + timedelta(seconds=10),
            retry_policy=policy,
        )
        restart_db.expire_all()
        retry_waiting = restart_db.get(Prediction, prediction_id)
        assert retry_waiting is not None
        assert retry_waiting.status == PredictionStatus.PROCESSING.value
        assert retry_waiting.next_attempt_at == current_time + timedelta(seconds=15)
    finally:
        restart_db.close()


def test_stale_attempt_cannot_overwrite_reclaimed_attempt(db: Session) -> None:
    policy = PredictionRetryPolicy(
        max_attempts=3,
        retry_delay_seconds=5,
        attempt_lease_seconds=10,
    )
    started_at = datetime(2026, 8, 20, 10, 0, 0)
    prediction = create_prediction(db, created_at=started_at - timedelta(seconds=1))
    old_claim = _claim_next_prediction(db, now=started_at, retry_policy=policy)
    assert old_claim is not None

    replacement_db = SessionLocal()
    try:
        assert _recover_one_stale_prediction(
            replacement_db,
            now=started_at + timedelta(seconds=10),
            retry_policy=policy,
        )
        new_claim = _claim_next_prediction(
            replacement_db,
            now=started_at + timedelta(seconds=15),
            retry_policy=policy,
        )
        assert new_claim is not None
        assert new_claim.attempt == 2

        assert not _persist_success(
            db,
            claim=old_claim,
            result=result_for("package-stale-old-v1"),
            retry_policy=policy,
            now=started_at + timedelta(seconds=16),
        )
        assert _persist_success(
            replacement_db,
            claim=new_claim,
            result=result_for("package-current-v1"),
            retry_policy=policy,
            now=started_at + timedelta(seconds=16),
        )
        assert not _persist_success(
            db,
            claim=old_claim,
            result=result_for("package-stale-old-v1"),
            retry_policy=policy,
            now=started_at + timedelta(seconds=17),
        )
    finally:
        replacement_db.close()

    db.expire_all()
    completed = db.get(Prediction, prediction.id)
    assert completed is not None
    assert completed.status == PredictionStatus.COMPLETED.value
    assert completed.attempt_count == 2
    assert completed.model_version == "package-current-v1"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0, "retry_delay_seconds": 1, "attempt_lease_seconds": 1},
        {
            "max_attempts": 1.5,
            "retry_delay_seconds": 1,
            "attempt_lease_seconds": 1,
        },
        {"max_attempts": 1, "retry_delay_seconds": 0, "attempt_lease_seconds": 1},
        {
            "max_attempts": 1,
            "retry_delay_seconds": float("nan"),
            "attempt_lease_seconds": 1,
        },
        {
            "max_attempts": 1,
            "retry_delay_seconds": float("inf"),
            "attempt_lease_seconds": 1,
        },
        {"max_attempts": 1, "retry_delay_seconds": 1, "attempt_lease_seconds": 0},
        {
            "max_attempts": 1,
            "retry_delay_seconds": 1,
            "attempt_lease_seconds": float("nan"),
        },
        {
            "max_attempts": 1,
            "retry_delay_seconds": 1,
            "attempt_lease_seconds": float("inf"),
        },
    ],
)
def test_retry_policy_rejects_invalid_values(kwargs: dict[str, float | int]) -> None:
    with pytest.raises(ValueError):
        PredictionRetryPolicy(**kwargs)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("WORKER_RETRY_DELAY_SECONDS", float("nan")),
        ("WORKER_RETRY_DELAY_SECONDS", float("inf")),
        ("WORKER_ATTEMPT_LEASE_SECONDS", float("nan")),
        ("WORKER_ATTEMPT_LEASE_SECONDS", float("inf")),
    ],
)
def test_settings_reject_non_finite_worker_timing(
    field_name: str,
    invalid_value: float,
) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field_name: invalid_value})
