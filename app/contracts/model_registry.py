"""Versioned contracts for candidate registration and controlled promotion."""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MODEL_REGISTRY_SCHEMA_VERSION = "vddai.model_registry.v1"
MODEL_REGISTRY_CODE_VERSION = "vddai.model_registry.sqlite.v1"


class ModelStage(str, Enum):
    CANDIDATE = "candidate"
    STAGING = "staging"
    PRODUCTION = "production"


class PromotionAction(str, Enum):
    PROMOTE = "promote"
    ROLLBACK = "rollback"


class PromotionOutcome(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def build_model_version(*, package_id: str, package_manifest_sha256: str) -> str:
    """Build the immutable public version from package identity and contents."""
    digest = package_manifest_sha256.removeprefix("sha256:")
    if (
        not package_manifest_sha256.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("package_manifest_sha256 must be canonical SHA-256")
    version = f"{package_id}-{digest[:12]}"
    if len(version) > 100:
        raise ValueError("Derived model version exceeds the registry limit")
    return version


class CandidateMetrics(BaseModel):
    """Finite scalar evidence attached to one candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    values: dict[str, float] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def validate_metrics(cls, values: dict[str, float]) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for name, value in values.items():
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("Metric names must be non-empty")
            if isinstance(value, bool) or not math.isfinite(value):
                raise ValueError("Candidate metrics must be finite numbers")
            normalized[clean_name] = float(value)
        return normalized


class ModelCandidate(BaseModel):
    """Immutable registration metadata for one complete inference package."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["vddai.model_registry.v1"] = MODEL_REGISTRY_SCHEMA_VERSION
    model_version: str = Field(
        min_length=8,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9-]+$",
    )
    package_id: str = Field(
        min_length=8,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9-]+$",
    )
    experiment_run_id: str = Field(min_length=1, max_length=100)
    package_manifest_path: str = Field(min_length=1)
    package_manifest_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    feature_bank_dir: str = Field(min_length=1)
    feature_bank_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dataset_name: Literal["MVTec AD"]
    dataset_category: Literal["tile"]
    dataset_version: str = Field(min_length=1)
    manifest_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    code_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    metrics: CandidateMetrics
    registered_by: str = Field(min_length=1, max_length=200)
    registered_at: datetime

    @field_validator("package_manifest_path", "feature_bank_dir")
    @classmethod
    def validate_repository_relative_path(cls, value: str) -> str:
        posix_path = PurePosixPath(value)
        windows_path = PureWindowsPath(value)
        if (
            "\\" in value
            or posix_path.is_absolute()
            or windows_path.is_absolute()
            or ".." in posix_path.parts
            or ".." in windows_path.parts
        ):
            raise ValueError("Artifact paths must be repository-relative")
        return posix_path.as_posix()

    @field_validator("registered_at")
    @classmethod
    def validate_registered_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("registered_at must include timezone")
        return value

    @model_validator(mode="after")
    def validate_immutable_version(self) -> ModelCandidate:
        expected = build_model_version(
            package_id=self.package_id,
            package_manifest_sha256=self.package_manifest_sha256,
        )
        if self.model_version != expected:
            raise ValueError("model_version must match the immutable naming rule")
        return self


class PromotionCriteria(BaseModel):
    """Predeclared minimum metric gates for one promotion decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    minimum_metrics: dict[str, float] = Field(min_length=1)

    @field_validator("minimum_metrics")
    @classmethod
    def validate_minimum_metrics(cls, values: dict[str, float]) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for name, value in values.items():
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("Promotion metric names must be non-empty")
            if isinstance(value, bool) or not math.isfinite(value):
                raise ValueError("Promotion metric thresholds must be finite")
            normalized[clean_name] = float(value)
        return normalized


class SmokeInferenceEvidence(BaseModel):
    """Public-safe evidence that one loaded package completed inference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    package_id: str = Field(min_length=8, max_length=80)
    anomaly_score: float
    threshold: float
    predicted_label: Literal["normal", "anomalous"]

    @field_validator("anomaly_score", "threshold")
    @classmethod
    def validate_finite_values(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Smoke-inference values must be finite")
        return value

    @model_validator(mode="after")
    def validate_decision_semantics(self) -> SmokeInferenceEvidence:
        expected = "anomalous" if self.anomaly_score > self.threshold else "normal"
        if self.predicted_label != expected:
            raise ValueError("Smoke-inference label violates score semantics")
        return self
