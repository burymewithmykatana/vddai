"""Versioned contracts shared by API, workers, and inference adapters."""

from app.contracts.inference import (
    INFERENCE_CONTRACT_SCHEMA_VERSION,
    MODEL_PACKAGE_SCHEMA_VERSION,
    ONLINE_INPUT_CONTRACT,
    PREPROCESSING_SCHEMA_VERSION,
    AnomalyInferenceResult,
    InferencePackageLineage,
    PredictionFailureCode,
    PredictionLabel,
    classify_anomaly_score,
)

__all__ = [
    "INFERENCE_CONTRACT_SCHEMA_VERSION",
    "MODEL_PACKAGE_SCHEMA_VERSION",
    "ONLINE_INPUT_CONTRACT",
    "PREPROCESSING_SCHEMA_VERSION",
    "AnomalyInferenceResult",
    "InferencePackageLineage",
    "PredictionFailureCode",
    "PredictionLabel",
    "classify_anomaly_score",
]
