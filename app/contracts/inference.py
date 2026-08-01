"""Executable v1 production inference contract.

This module owns serving semantics shared by artifact loading, worker
inference, persistence, and API serialization. It must not load artifacts or
perform inference itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

INFERENCE_CONTRACT_SCHEMA_VERSION = "vddai.production_inference.v1"
PREPROCESSING_SCHEMA_VERSION = "vddai.preprocessing.rgb_chw_bilinear.v1"
MODEL_PACKAGE_SCHEMA_VERSION = "vddai.inference_package.v1"

SCORE_DIRECTION = "higher_is_more_anomalous"
ANOMALOUS_THRESHOLD_RULE = "score > threshold"
NORMAL_THRESHOLD_RULE = "score <= threshold"
EXPECTED_PREDICTION_SEMANTICS = {
    "anomalous": ANOMALOUS_THRESHOLD_RULE,
    "normal": NORMAL_THRESHOLD_RULE,
}


class PredictionLabel(str, Enum):
    NORMAL = "normal"
    ANOMALOUS = "anomalous"


class PredictionFailureCode(str, Enum):
    """Stable public failure code; internal exception text remains private."""

    INFERENCE_FAILED = "inference_failed"


class OnlineInputContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["vddai.preprocessing.rgb_chw_bilinear.v1"]
    source: Literal["server_controlled_stored_image_path"]
    storage_tensor_shape: tuple[int, int, int]
    extractor_batch_shape: tuple[None, int, int, int]
    dtype: Literal["torch.float32"]
    numeric_range: tuple[float, float]
    color_channels: Literal["RGB"]
    orientation_policy: Literal["exif_transpose"]
    resize_policy: Literal["bilinear_exact_size"]
    crop_policy: Literal["none"]
    model_normalization_owner: Literal["resnet18_feature_adapter"]


ONLINE_INPUT_CONTRACT = OnlineInputContract(
    schema_version=PREPROCESSING_SCHEMA_VERSION,
    source="server_controlled_stored_image_path",
    storage_tensor_shape=(3, 224, 224),
    extractor_batch_shape=(None, 3, 224, 224),
    dtype="torch.float32",
    numeric_range=(0.0, 1.0),
    color_channels="RGB",
    orientation_policy="exif_transpose",
    resize_policy="bilinear_exact_size",
    crop_policy="none",
    model_normalization_owner="resnet18_feature_adapter",
)


class InferencePackageLineage(BaseModel):
    """Public-safe frozen package identity persisted with completed results."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_schema_version: Literal["vddai.production_inference.v1"]
    schema_version: Literal["vddai.inference_package.v1"]
    package_id: str = Field(
        min_length=8,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9-]+$",
    )
    preprocessing_schema_version: Literal["vddai.preprocessing.rgb_chw_bilinear.v1"]
    dataset_name: Literal["MVTec AD"]
    dataset_category: Literal["tile"]
    dataset_version: str = Field(min_length=1)
    manifest_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    feature_bank_schema_version: str = Field(min_length=1)
    feature_bank_code_version: str = Field(min_length=1)
    feature_bank_path: str = Field(min_length=1)
    feature_bank_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    feature_bank_sample_count: int = Field(gt=0)
    extractor_name: Literal["torchvision.resnet18"]
    extractor_weights: Literal["IMAGENET1K_V1"]
    extractor_layer: Literal["avgpool"]
    feature_dimension: Literal[512]
    scorer_distance: Literal["euclidean"]
    scorer_aggregation: Literal["mean_k_nearest"]
    scorer_k: int = Field(gt=0)
    threshold_policy: Literal["normal_validation_quantile"]
    threshold_quantile: float = Field(ge=0.0, le=1.0)
    threshold_value: float
    threshold_artifact_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @field_validator("feature_bank_path")
    @classmethod
    def validate_package_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if "\\" in value or path.is_absolute() or ".." in path.parts:
            raise ValueError("feature_bank_path must be package-relative")
        return value

    @field_validator("threshold_value")
    @classmethod
    def validate_finite_threshold(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("threshold_value must be finite")
        return value


def classify_anomaly_score(
    *,
    score: float,
    threshold: float,
) -> PredictionLabel:
    """Apply the frozen strict-greater-than image-level decision rule."""
    if not math.isfinite(score) or not math.isfinite(threshold):
        raise ValueError("Anomaly score and threshold must be finite.")
    if score > threshold:
        return PredictionLabel.ANOMALOUS
    return PredictionLabel.NORMAL


@dataclass(frozen=True)
class AnomalyInferenceResult:
    """Typed worker result produced only after successful inference."""

    predicted_label: PredictionLabel
    anomaly_score: float
    threshold: float
    model_version: str
    model_lineage: InferencePackageLineage
    latency_ms: int

    def __post_init__(self) -> None:
        expected_label = classify_anomaly_score(
            score=self.anomaly_score,
            threshold=self.threshold,
        )
        if self.predicted_label != expected_label:
            raise ValueError("Prediction label does not match score and threshold.")
        if self.model_version != self.model_lineage.package_id:
            raise ValueError("Model version must match the frozen package identifier.")
        if self.threshold != self.model_lineage.threshold_value:
            raise ValueError("Result threshold must match frozen package lineage.")
        if self.latency_ms < 0:
            raise ValueError("Inference latency must be non-negative.")

    def lineage_for_persistence(self) -> dict[str, object]:
        return self.model_lineage.model_dump(mode="json")
