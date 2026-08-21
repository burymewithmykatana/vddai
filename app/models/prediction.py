import math
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.contracts.inference import (
    AnomalyInferenceResult,
    PredictionFailureCode,
    PredictionLabel,
)
from app.db.base import Base


class PredictionStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Keep the physical column name for compatibility; values are opaque keys.
    image_object_key: Mapped[str] = mapped_column(
        "image_path",
        String(500),
        nullable=False,
    )

    image_format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    image_width: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    image_height: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default=PredictionStatus.QUEUED.value,
        nullable=False,
        index=True,
    )

    predicted_label: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    anomaly_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    threshold: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    model_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    model_lineage: Mapped[dict[str, object] | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
    )

    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )

    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    @property
    def failure_code(self) -> str | None:
        """Expose only a stable public code; keep error_message internal."""
        if self.status == PredictionStatus.FAILED.value:
            return PredictionFailureCode.INFERENCE_FAILED.value
        return None

    @validates("status")
    def validate_status(self, key: str, value: str | PredictionStatus) -> str:
        normalized = value.value if isinstance(value, PredictionStatus) else value
        if normalized not in {status.value for status in PredictionStatus}:
            raise ValueError("Prediction status is outside the lifecycle vocabulary.")
        return normalized

    @validates("predicted_label")
    def validate_predicted_label(
        self,
        key: str,
        value: str | PredictionLabel | None,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.value if isinstance(value, PredictionLabel) else value
        if normalized not in {label.value for label in PredictionLabel}:
            raise ValueError("Prediction label is outside the inference vocabulary.")
        return normalized

    @validates("anomaly_score", "threshold")
    def validate_finite_result_number(
        self,
        key: str,
        value: float | None,
    ) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError(f"{key} must be finite when persisted.")
        return value

    @validates("latency_ms")
    def validate_latency(self, key: str, value: int | None) -> int | None:
        if value is not None and (isinstance(value, bool) or value < 0):
            raise ValueError("latency_ms must be a non-negative integer.")
        return value

    @validates("attempt_count")
    def validate_attempt_count(self, key: str, value: int) -> int:
        if isinstance(value, bool) or value < 0:
            raise ValueError("attempt_count must be a non-negative integer.")
        return value

    @validates("processing_started_at", "lease_expires_at", "next_attempt_at")
    def validate_lifecycle_timestamp_column(
        self,
        key: str,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None:
            self._validate_lifecycle_timestamp(value, field=key)
        return value

    @staticmethod
    def _validate_lifecycle_timestamp(value: datetime, *, field: str) -> None:
        if value.tzinfo is not None:
            raise ValueError(f"{field} must use timezone-naive UTC.")

    def clear_inference_result(self) -> None:
        self.predicted_label = None
        self.confidence = None
        self.anomaly_score = None
        self.threshold = None
        self.model_version = None
        self.model_lineage = None
        self.latency_ms = None

    def _require_current_processing_attempt(self, *, expected_attempt: int) -> None:
        if (
            self.status != PredictionStatus.PROCESSING.value
            or self.processing_started_at is None
        ):
            raise ValueError("A timestamped processing prediction is required.")
        if self.attempt_count != expected_attempt:
            raise ValueError("Prediction attempt token is stale.")
        if self.next_attempt_at is not None:
            raise ValueError("A retry-waiting prediction has no active attempt.")

    def start_processing(
        self,
        *,
        at: datetime,
        lease_expires_at: datetime,
    ) -> int:
        if self.attempt_count is None:
            self.attempt_count = 0
        is_initial_attempt = self.status == PredictionStatus.QUEUED.value
        is_due_retry = (
            self.status == PredictionStatus.PROCESSING.value
            and self.processing_started_at is not None
            and self.lease_expires_at is None
            and self.next_attempt_at is not None
            and at >= self.next_attempt_at
        )
        if not is_initial_attempt and not is_due_retry:
            raise ValueError("Prediction is not eligible to start an attempt.")
        self._validate_lifecycle_timestamp(at, field="processing_started_at")
        self._validate_lifecycle_timestamp(
            lease_expires_at,
            field="lease_expires_at",
        )
        if self.created_at is not None and at < self.created_at:
            raise ValueError("processing_started_at cannot precede created_at.")
        if lease_expires_at <= at:
            raise ValueError("lease_expires_at must follow the attempt start.")
        if is_initial_attempt:
            if self.attempt_count != 0:
                raise ValueError("Queued predictions cannot have prior attempts.")
            self.processing_started_at = at
        self.clear_inference_result()
        self.status = PredictionStatus.PROCESSING.value
        self.attempt_count += 1
        self.lease_expires_at = lease_expires_at
        self.next_attempt_at = None
        self.completed_at = None
        self.error_message = None
        return self.attempt_count

    def schedule_retry(
        self,
        *,
        expected_attempt: int,
        error_message: str,
        next_attempt_at: datetime,
    ) -> None:
        self._require_current_processing_attempt(expected_attempt=expected_attempt)
        if not error_message.strip():
            raise ValueError("Retrying predictions require an internal diagnostic.")
        self._validate_lifecycle_timestamp(
            next_attempt_at,
            field="next_attempt_at",
        )
        if next_attempt_at < self.processing_started_at:
            raise ValueError("next_attempt_at cannot precede processing_started_at.")
        self.clear_inference_result()
        self.lease_expires_at = None
        self.next_attempt_at = next_attempt_at
        self.completed_at = None
        self.error_message = error_message

    def fail_retry_waiting(
        self,
        *,
        expected_attempt: int,
        error_message: str,
        at: datetime,
    ) -> None:
        if (
            self.status != PredictionStatus.PROCESSING.value
            or self.processing_started_at is None
            or self.lease_expires_at is not None
            or self.next_attempt_at is None
        ):
            raise ValueError("A retry-waiting prediction is required.")
        if self.attempt_count != expected_attempt:
            raise ValueError("Prediction attempt token is stale.")
        if not error_message.strip():
            raise ValueError("Failed predictions require an internal diagnostic.")
        self._validate_lifecycle_timestamp(at, field="completed_at")
        if at < self.processing_started_at:
            raise ValueError("completed_at cannot precede processing_started_at.")
        self.clear_inference_result()
        self.status = PredictionStatus.FAILED.value
        self.lease_expires_at = None
        self.next_attempt_at = None
        self.error_message = error_message
        self.completed_at = at

    def complete(
        self,
        result: AnomalyInferenceResult,
        *,
        expected_attempt: int,
        at: datetime,
    ) -> None:
        self._require_current_processing_attempt(expected_attempt=expected_attempt)
        if self.lease_expires_at is None:
            raise ValueError("Completed predictions require an active attempt lease.")
        self._validate_lifecycle_timestamp(at, field="completed_at")
        if at < self.processing_started_at:
            raise ValueError("completed_at cannot precede processing_started_at.")
        self.predicted_label = result.predicted_label
        self.confidence = None
        self.anomaly_score = result.anomaly_score
        self.threshold = result.threshold
        self.model_version = result.model_version
        self.model_lineage = result.lineage_for_persistence()
        self.latency_ms = result.latency_ms
        self.status = PredictionStatus.COMPLETED.value
        self.lease_expires_at = None
        self.next_attempt_at = None
        self.completed_at = at
        self.error_message = None

    def fail(
        self,
        *,
        expected_attempt: int,
        error_message: str,
        at: datetime,
    ) -> None:
        self._require_current_processing_attempt(expected_attempt=expected_attempt)
        if not error_message.strip():
            raise ValueError("Failed predictions require an internal diagnostic.")
        self._validate_lifecycle_timestamp(at, field="completed_at")
        if at < self.processing_started_at:
            raise ValueError("completed_at cannot precede processing_started_at.")
        self.clear_inference_result()
        self.status = PredictionStatus.FAILED.value
        self.lease_expires_at = None
        self.next_attempt_at = None
        self.error_message = error_message
        self.completed_at = at

    user = relationship(
        "User",
        back_populates="predictions",
    )
