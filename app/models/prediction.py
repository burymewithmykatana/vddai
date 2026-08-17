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

    def start_processing(self, *, at: datetime) -> None:
        if self.status != PredictionStatus.QUEUED.value:
            raise ValueError("Only queued predictions can start processing.")
        self._validate_lifecycle_timestamp(at, field="processing_started_at")
        if self.created_at is not None and at < self.created_at:
            raise ValueError("processing_started_at cannot precede created_at.")
        self.clear_inference_result()
        self.status = PredictionStatus.PROCESSING.value
        self.processing_started_at = at
        self.completed_at = None
        self.error_message = None

    def complete(
        self,
        result: AnomalyInferenceResult,
        *,
        at: datetime,
    ) -> None:
        if (
            self.status != PredictionStatus.PROCESSING.value
            or self.processing_started_at is None
        ):
            raise ValueError(
                "Only a timestamped processing prediction can be completed."
            )
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
        self.completed_at = at
        self.error_message = None

    def fail(self, *, error_message: str, at: datetime) -> None:
        if (
            self.status != PredictionStatus.PROCESSING.value
            or self.processing_started_at is None
        ):
            raise ValueError("Only a timestamped processing prediction can fail.")
        if not error_message.strip():
            raise ValueError("Failed predictions require an internal diagnostic.")
        self._validate_lifecycle_timestamp(at, field="completed_at")
        if at < self.processing_started_at:
            raise ValueError("completed_at cannot precede processing_started_at.")
        self.clear_inference_result()
        self.status = PredictionStatus.FAILED.value
        self.error_message = error_message
        self.completed_at = at

    user = relationship(
        "User",
        back_populates="predictions",
    )
