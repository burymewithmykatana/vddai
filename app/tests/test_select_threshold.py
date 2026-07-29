import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ml.score_anomalies import (
    SCORE_ARTIFACT_CODE_VERSION,
    SCORE_ARTIFACT_SCHEMA_VERSION,
)
from ml.select_threshold import (
    THRESHOLD_ARTIFACT_CODE_VERSION,
    THRESHOLD_ARTIFACT_SCHEMA_VERSION,
    select_threshold_artifact,
)


FIXED_CREATED_AT = datetime(
    2026,
    7,
    29,
    16,
    0,
    tzinfo=timezone.utc,
)


def create_score_artifact(path: Path) -> None:
    payload = {
        "schema_version": SCORE_ARTIFACT_SCHEMA_VERSION,
        "code_version": SCORE_ARTIFACT_CODE_VERSION,
        "dataset": {
            "name": "fake",
            "category": "tile",
            "version": "fake-dataset-v1",
            "manifest_fingerprint": "sha256:manifest",
        },
        "feature_bank": {
            "schema_version": "vddai.feature_bank.v1",
            "code_version": "vddai.feature_bank.generator.v1",
            "dataset_version": "fake-dataset-v1",
            "sample_count": 4,
            "split": "train",
            "features_sha256": "sha256:features",
        },
        "feature_extractor": {
            "name": "test.fake",
            "pretrained_weights": "none",
            "feature_layer": "mean",
            "feature_dimension": 2,
            "normalization": {
                "operation": "none",
                "mean": [0.0, 0.0, 0.0],
                "std": [1.0, 1.0, 1.0],
            },
        },
        "scorer": {
            "distance": "euclidean",
            "aggregation": "mean_k_nearest",
            "k": 1,
            "higher_is_more_anomalous": True,
        },
        "records": [
            {
                "sample_id": "validation-001",
                "split": "validation",
                "label": 0,
                "defect_type": "good",
                "anomaly_score": 1.0,
                "has_mask": False,
                "source_path": "train/good/001.png",
            },
            {
                "sample_id": "validation-002",
                "split": "validation",
                "label": 0,
                "defect_type": "good",
                "anomaly_score": 2.0,
                "has_mask": False,
                "source_path": "train/good/002.png",
            },
            {
                "sample_id": "validation-003",
                "split": "validation",
                "label": 0,
                "defect_type": "good",
                "anomaly_score": 3.0,
                "has_mask": False,
                "source_path": "train/good/003.png",
            },
            {
                "sample_id": "validation-004",
                "split": "validation",
                "label": 0,
                "defect_type": "good",
                "anomaly_score": 4.0,
                "has_mask": False,
                "source_path": "train/good/004.png",
            },
            {
                "sample_id": "test-anomaly-001",
                "split": "test",
                "label": 1,
                "defect_type": "crack",
                "anomaly_score": -1000.0,
                "has_mask": True,
                "source_path": "test/crack/001.png",
            },
        ],
    }
    path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def test_threshold_artifact_uses_validation_only_and_keeps_lineage(
    tmp_path: Path,
) -> None:
    score_artifact_path = tmp_path / "scores.json"
    create_score_artifact(score_artifact_path)

    artifact = select_threshold_artifact(
        score_artifact_path=score_artifact_path,
        artifact_dir=tmp_path / "threshold",
        quantile=0.5,
        created_at=FIXED_CREATED_AT,
    )

    assert artifact.selection.threshold == pytest.approx(
        2.5
    )
    assert artifact.selection.validation_sample_count == 4

    payload = json.loads(
        artifact.threshold_path.read_text(
            encoding="utf-8"
        )
    )
    assert payload["schema_version"] == (
        THRESHOLD_ARTIFACT_SCHEMA_VERSION
    )
    assert payload["code_version"] == (
        THRESHOLD_ARTIFACT_CODE_VERSION
    )
    assert payload["created_at"] == (
        "2026-07-29T16:00:00Z"
    )
    assert payload["calibration"] == {
        "split": "validation",
        "mode": "normal_only",
        "uses_test_scores": False,
        "uses_test_labels": False,
        "quantile_method": "linear",
    }
    assert payload["prediction_semantics"] == {
        "anomalous": "score > threshold",
        "normal": "score <= threshold",
    }
    assert payload["dataset"]["version"] == (
        "fake-dataset-v1"
    )
    assert payload["feature_bank"]["sample_count"] == 4
    assert payload["feature_extractor"]["name"] == (
        "test.fake"
    )
    assert payload["scorer"]["k"] == 1
    assert payload["threshold_selection"][
        "estimated_validation_false_positive_rate"
    ] == 0.5
    assert "records" not in payload

    assert payload["source_scores"][
        "validation_records_sha256"
    ].startswith(
        "sha256:"
    )
    assert not list(artifact.artifact_dir.glob(".*.tmp"))

    changed_score_path = tmp_path / "changed-test-scores.json"
    changed_score_payload = json.loads(
        score_artifact_path.read_text(encoding="utf-8")
    )
    changed_score_payload["records"][-1][
        "anomaly_score"
    ] = 1000.0
    changed_score_path.write_text(
        json.dumps(changed_score_payload, indent=2),
        encoding="utf-8",
    )

    changed_artifact = select_threshold_artifact(
        score_artifact_path=changed_score_path,
        artifact_dir=tmp_path / "changed-threshold",
        quantile=0.5,
        created_at=FIXED_CREATED_AT,
    )
    changed_payload = json.loads(
        changed_artifact.threshold_path.read_text(
            encoding="utf-8"
        )
    )

    assert changed_artifact.selection == artifact.selection
    assert changed_payload["source_scores"][
        "validation_records_sha256"
    ] == payload["source_scores"][
        "validation_records_sha256"
    ]
