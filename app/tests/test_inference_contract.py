from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.contracts.inference import (
    INFERENCE_CONTRACT_SCHEMA_VERSION,
    MODEL_PACKAGE_SCHEMA_VERSION,
    ONLINE_INPUT_CONTRACT,
    PREPROCESSING_SCHEMA_VERSION,
    SCORE_DIRECTION,
    AnomalyInferenceResult,
    InferencePackageLineage,
    PredictionFailureCode,
    PredictionLabel,
    classify_anomaly_score,
)
from app.models.prediction import Prediction, PredictionStatus
from app.schemas.prediction import PredictionRead


def valid_lineage(
    *,
    package_id: str = "mvtec-tile-resnet18-test0001",
    threshold: float = 2.0,
) -> InferencePackageLineage:
    return InferencePackageLineage(
        contract_schema_version=INFERENCE_CONTRACT_SCHEMA_VERSION,
        schema_version=MODEL_PACKAGE_SCHEMA_VERSION,
        package_id=package_id,
        preprocessing_schema_version=PREPROCESSING_SCHEMA_VERSION,
        dataset_name="MVTec AD",
        dataset_category="tile",
        dataset_version="dataset-v1",
        manifest_fingerprint=f"sha256:{'a' * 64}",
        feature_bank_schema_version="vddai.feature_bank.v1",
        feature_bank_code_version="vddai.feature_bank.generator.v1",
        feature_bank_path="features.npz",
        feature_bank_sha256=f"sha256:{'b' * 64}",
        feature_bank_sample_count=184,
        extractor_name="torchvision.resnet18",
        extractor_weights="IMAGENET1K_V1",
        extractor_layer="avgpool",
        feature_dimension=512,
        scorer_distance="euclidean",
        scorer_aggregation="mean_k_nearest",
        scorer_k=1,
        threshold_policy="normal_validation_quantile",
        threshold_quantile=0.95,
        threshold_value=threshold,
        threshold_artifact_sha256=f"sha256:{'c' * 64}",
    )


def base_prediction_payload() -> dict[str, object]:
    return {
        "id": 1,
        "user_id": 2,
        "image_format": "PNG",
        "image_width": 32,
        "image_height": 32,
        "status": PredictionStatus.QUEUED,
        "predicted_label": None,
        "confidence": None,
        "anomaly_score": None,
        "threshold": None,
        "model_version": None,
        "model_lineage": None,
        "latency_ms": None,
        "failure_code": None,
        "created_at": datetime.now(),
        "processing_started_at": None,
        "completed_at": None,
    }


def test_online_input_contract_is_exact_and_versioned() -> None:
    assert ONLINE_INPUT_CONTRACT.schema_version == PREPROCESSING_SCHEMA_VERSION
    assert ONLINE_INPUT_CONTRACT.source == "server_controlled_stored_image_path"
    assert ONLINE_INPUT_CONTRACT.storage_tensor_shape == (3, 224, 224)
    assert ONLINE_INPUT_CONTRACT.extractor_batch_shape == (None, 3, 224, 224)
    assert ONLINE_INPUT_CONTRACT.dtype == "torch.float32"
    assert ONLINE_INPUT_CONTRACT.numeric_range == (0.0, 1.0)
    assert ONLINE_INPUT_CONTRACT.color_channels == "RGB"
    assert ONLINE_INPUT_CONTRACT.orientation_policy == "exif_transpose"
    assert ONLINE_INPUT_CONTRACT.resize_policy == "bilinear_exact_size"
    assert ONLINE_INPUT_CONTRACT.crop_policy == "none"
    assert ONLINE_INPUT_CONTRACT.model_normalization_owner == (
        "resnet18_feature_adapter"
    )


def test_score_direction_and_strict_threshold_rule_are_frozen() -> None:
    assert SCORE_DIRECTION == "higher_is_more_anomalous"
    assert classify_anomaly_score(score=1.9, threshold=2.0) == (PredictionLabel.NORMAL)
    assert classify_anomaly_score(score=2.0, threshold=2.0) == (PredictionLabel.NORMAL)
    assert classify_anomaly_score(score=2.1, threshold=2.0) == (
        PredictionLabel.ANOMALOUS
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_scores_fail_fast(value: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        classify_anomaly_score(score=value, threshold=2.0)


def test_package_lineage_rejects_missing_extra_and_unsafe_fields() -> None:
    payload = valid_lineage().model_dump()
    payload.pop("feature_bank_sha256")
    with pytest.raises(ValidationError):
        InferencePackageLineage.model_validate(payload)

    payload = valid_lineage().model_dump()
    payload["unversioned_field"] = "drift"
    with pytest.raises(ValidationError):
        InferencePackageLineage.model_validate(payload)

    payload = valid_lineage().model_dump()
    payload["feature_bank_path"] = "../outside/features.npz"
    with pytest.raises(ValidationError, match="package-relative"):
        InferencePackageLineage.model_validate(payload)


def test_typed_result_enforces_label_package_and_threshold_consistency() -> None:
    lineage = valid_lineage(threshold=2.0)
    result = AnomalyInferenceResult(
        predicted_label=PredictionLabel.NORMAL,
        anomaly_score=2.0,
        threshold=2.0,
        model_version=lineage.package_id,
        model_lineage=lineage,
        latency_ms=12,
    )

    assert result.predicted_label == PredictionLabel.NORMAL
    assert set(result.lineage_for_persistence()) == set(
        InferencePackageLineage.model_fields
    )

    with pytest.raises(ValueError, match="label does not match"):
        AnomalyInferenceResult(
            predicted_label=PredictionLabel.ANOMALOUS,
            anomaly_score=2.0,
            threshold=2.0,
            model_version=lineage.package_id,
            model_lineage=lineage,
            latency_ms=12,
        )


def test_public_schema_keeps_confidence_null_and_hides_internal_error() -> None:
    queued_payload = base_prediction_payload()
    queued_payload["confidence"] = 0.99
    queued = PredictionRead.model_validate(queued_payload)

    assert queued.confidence is None
    assert "image_path" not in queued.model_dump()
    assert "error_message" not in queued.model_dump()

    failed_payload = base_prediction_payload()
    processing_started_at = datetime.now()
    failed_payload.update(
        {
            "status": PredictionStatus.FAILED,
            "failure_code": PredictionFailureCode.INFERENCE_FAILED,
            "processing_started_at": processing_started_at,
            "completed_at": processing_started_at + timedelta(milliseconds=1),
            "error_message": "C:/private/artifact/path: stack trace",
        }
    )
    failed = PredictionRead.model_validate(failed_payload)

    serialized = failed.model_dump(mode="json")
    assert serialized["failure_code"] == "inference_failed"
    assert "error_message" not in serialized
    assert "private" not in str(serialized)


def test_public_schema_rejects_lifecycle_and_serialization_drift() -> None:
    invalid_queued = base_prediction_payload()
    invalid_queued["anomaly_score"] = 3.0
    with pytest.raises(ValidationError, match="cannot expose results"):
        PredictionRead.model_validate(invalid_queued)

    completed = base_prediction_payload()
    lineage = valid_lineage(threshold=2.0)
    processing_started_at = datetime.now()
    completed.update(
        {
            "status": PredictionStatus.COMPLETED,
            "predicted_label": PredictionLabel.NORMAL,
            "anomaly_score": 2.0,
            "threshold": 2.0,
            "model_version": lineage.package_id,
            "model_lineage": lineage,
            "latency_ms": 8,
            "processing_started_at": processing_started_at,
            "completed_at": processing_started_at + timedelta(milliseconds=1),
        }
    )
    serialized = PredictionRead.model_validate(completed).model_dump(mode="json")

    assert serialized["predicted_label"] == "normal"
    assert serialized["anomaly_score"] == 2.0
    assert serialized["confidence"] is None

    completed["threshold"] = 2.1
    with pytest.raises(ValidationError, match="Threshold does not match"):
        PredictionRead.model_validate(completed)


def test_public_schema_enforces_lifecycle_timestamps() -> None:
    processing = base_prediction_payload()
    processing.update(
        {
            "status": PredictionStatus.PROCESSING,
            "processing_started_at": processing["created_at"],
        }
    )
    serialized = PredictionRead.model_validate(processing).model_dump(mode="json")
    assert serialized["processing_started_at"] is not None

    processing["processing_started_at"] = None
    with pytest.raises(ValidationError, match="processing timestamp"):
        PredictionRead.model_validate(processing)

    failed = base_prediction_payload()
    failed.update(
        {
            "status": PredictionStatus.FAILED,
            "failure_code": PredictionFailureCode.INFERENCE_FAILED,
            "processing_started_at": failed["created_at"] + timedelta(seconds=1),
            "completed_at": failed["created_at"],
        }
    )
    with pytest.raises(ValidationError, match="cannot precede"):
        PredictionRead.model_validate(failed)


def test_prediction_domain_atomically_completes_full_result() -> None:
    created_at = datetime(2026, 8, 3, 12, 0, 0)
    prediction = Prediction(
        user_id=1,
        image_object_key="predictions/internal.png",
        image_format="PNG",
        image_width=32,
        image_height=32,
        status=PredictionStatus.QUEUED,
        created_at=created_at,
    )
    lineage = valid_lineage(threshold=2.0)
    result = AnomalyInferenceResult(
        predicted_label=PredictionLabel.NORMAL,
        anomaly_score=2.0,
        threshold=2.0,
        model_version=lineage.package_id,
        model_lineage=lineage,
        latency_ms=8,
    )
    processing_started_at = created_at + timedelta(seconds=1)
    completed_at = processing_started_at + timedelta(milliseconds=8)

    with pytest.raises(ValueError, match="timestamped processing"):
        prediction.complete(result, at=completed_at)

    prediction.start_processing(at=processing_started_at)
    prediction.complete(result, at=completed_at)

    assert prediction.status == PredictionStatus.COMPLETED.value
    assert prediction.predicted_label == PredictionLabel.NORMAL.value
    assert prediction.anomaly_score == 2.0
    assert prediction.threshold == 2.0
    assert prediction.model_version == lineage.package_id
    assert prediction.model_lineage == lineage.model_dump(mode="json")
    assert prediction.latency_ms == 8
    assert prediction.confidence is None
    assert prediction.processing_started_at == processing_started_at
    assert prediction.completed_at == completed_at


def test_prediction_domain_failure_clears_stale_result() -> None:
    created_at = datetime(2026, 8, 3, 12, 0, 0)
    prediction = Prediction(
        user_id=1,
        image_object_key="predictions/internal.png",
        image_format="PNG",
        image_width=32,
        image_height=32,
        status=PredictionStatus.QUEUED,
        created_at=created_at,
        predicted_label=PredictionLabel.ANOMALOUS,
        anomaly_score=4.0,
        threshold=2.0,
        model_version="stale-package",
        model_lineage={"stale": True},
        latency_ms=20,
    )
    processing_started_at = created_at + timedelta(seconds=1)

    prediction.start_processing(at=processing_started_at)
    prediction.fail(
        error_message="RuntimeError: safe internal diagnostic",
        at=processing_started_at + timedelta(seconds=1),
    )

    assert prediction.status == PredictionStatus.FAILED.value
    assert prediction.predicted_label is None
    assert prediction.anomaly_score is None
    assert prediction.threshold is None
    assert prediction.model_version is None
    assert prediction.model_lineage is None
    assert prediction.latency_ms is None
    assert prediction.completed_at is not None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_prediction_domain_rejects_non_finite_persisted_numbers(value: float) -> None:
    prediction = Prediction()
    with pytest.raises(ValueError, match="must be finite"):
        prediction.anomaly_score = value
    with pytest.raises(ValueError, match="must be finite"):
        prediction.threshold = value


def test_prediction_domain_rejects_invalid_values_and_aware_timestamps() -> None:
    prediction = Prediction()
    with pytest.raises(ValueError, match="status"):
        prediction.status = "invented"
    with pytest.raises(ValueError, match="label"):
        prediction.predicted_label = "defective"
    with pytest.raises(ValueError, match="non-negative"):
        prediction.latency_ms = -1

    prediction.status = PredictionStatus.QUEUED
    prediction.created_at = datetime(2026, 8, 3, 12, 0, 0)
    with pytest.raises(ValueError, match="timezone-naive UTC"):
        prediction.start_processing(at=datetime.now(UTC))
