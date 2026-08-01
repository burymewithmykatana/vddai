from datetime import UTC, datetime

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
from app.models.prediction import PredictionStatus
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
        "image_path": "uploads/server-controlled.png",
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
        "created_at": datetime.now(UTC),
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
    assert "error_message" not in queued.model_dump()

    failed_payload = base_prediction_payload()
    failed_payload.update(
        {
            "status": PredictionStatus.FAILED,
            "failure_code": PredictionFailureCode.INFERENCE_FAILED,
            "completed_at": datetime.now(UTC),
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
    completed.update(
        {
            "status": PredictionStatus.COMPLETED,
            "predicted_label": PredictionLabel.NORMAL,
            "anomaly_score": 2.0,
            "threshold": 2.0,
            "model_version": lineage.package_id,
            "model_lineage": lineage,
            "latency_ms": 8,
            "completed_at": datetime.now(UTC),
        }
    )
    serialized = PredictionRead.model_validate(completed).model_dump(mode="json")

    assert serialized["predicted_label"] == "normal"
    assert serialized["anomaly_score"] == 2.0
    assert serialized["confidence"] is None

    completed["threshold"] = 2.1
    with pytest.raises(ValidationError, match="Threshold does not match"):
        PredictionRead.model_validate(completed)
