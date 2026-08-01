from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contracts.inference import (
    InferencePackageLineage,
    PredictionFailureCode,
    PredictionLabel,
    classify_anomaly_score,
)
from app.models.prediction import PredictionStatus


class PredictionQueuedResponse(BaseModel):
    prediction_id: int
    status: str
    message: str


class PredictionRead(BaseModel):
    id: int
    user_id: int
    image_path: str
    image_format: str
    image_width: int
    image_height: int
    status: PredictionStatus
    predicted_label: PredictionLabel | None = Field(
        description="Image-level decision derived from score and threshold."
    )
    confidence: None = Field(
        default=None,
        description=(
            "Deprecated compatibility field. Anomaly distance is exposed "
            "only as anomaly_score and is not a probability."
        ),
    )
    anomaly_score: float | None = Field(
        description=(
            "Exact Euclidean anomaly distance; higher is more anomalous. "
            "This is not a probability."
        )
    )
    threshold: float | None = Field(
        description="Frozen normal-validation threshold used for the decision."
    )
    model_version: str | None = Field(
        description="Stable identifier of the complete frozen inference package."
    )
    model_lineage: InferencePackageLineage | None = Field(
        description="Versioned public-safe package lineage."
    )
    latency_ms: int | None = Field(
        default=None,
        ge=0,
        description="Worker inference latency in milliseconds.",
    )
    failure_code: PredictionFailureCode | None = Field(
        description="Stable public failure code without internal exception details."
    )
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("confidence", mode="before")
    @classmethod
    def hide_legacy_confidence(cls, value: object) -> None:
        return None

    @model_validator(mode="after")
    def validate_lifecycle_contract(self) -> "PredictionRead":
        result_values = (
            self.predicted_label,
            self.anomaly_score,
            self.threshold,
            self.model_version,
            self.model_lineage,
            self.latency_ms,
        )

        if self.status in {
            PredictionStatus.QUEUED,
            PredictionStatus.PROCESSING,
        }:
            if any(value is not None for value in result_values):
                raise ValueError(
                    "Queued and processing predictions cannot expose results."
                )
            if self.completed_at is not None or self.failure_code is not None:
                raise ValueError(
                    "Queued and processing predictions cannot be terminal."
                )

        if self.status in {
            PredictionStatus.COMPLETED,
            PredictionStatus.NEEDS_REVIEW,
        }:
            if any(value is None for value in result_values):
                raise ValueError(
                    "Completed predictions require the full inference result."
                )
            if self.completed_at is None or self.failure_code is not None:
                raise ValueError(
                    "Completed predictions require a successful terminal state."
                )
            assert self.anomaly_score is not None
            assert self.threshold is not None
            assert self.predicted_label is not None
            assert self.model_version is not None
            assert self.model_lineage is not None
            if self.predicted_label != classify_anomaly_score(
                score=self.anomaly_score,
                threshold=self.threshold,
            ):
                raise ValueError("Prediction label does not match score and threshold.")
            if self.model_version != self.model_lineage.package_id:
                raise ValueError("Model version does not match package lineage.")
            if self.threshold != self.model_lineage.threshold_value:
                raise ValueError("Threshold does not match package lineage.")

        if self.status == PredictionStatus.FAILED:
            if any(value is not None for value in result_values):
                raise ValueError("Failed predictions cannot expose results.")
            if (
                self.completed_at is None
                or self.failure_code != PredictionFailureCode.INFERENCE_FAILED
            ):
                raise ValueError(
                    "Failed predictions require a safe terminal failure code."
                )

        return self
