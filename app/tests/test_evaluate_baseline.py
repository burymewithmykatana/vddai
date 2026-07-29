import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ml.evaluate_baseline import (
    EVALUATION_CODE_VERSION,
    EVALUATION_SCHEMA_VERSION,
    RUN_MANIFEST_FILENAME,
    EvaluationRunError,
    generate_evaluation_run,
)
from ml.score_anomalies import (
    SCORE_ARTIFACT_CODE_VERSION,
    SCORE_ARTIFACT_SCHEMA_VERSION,
)

FIXED_CREATED_AT = datetime(
    2026,
    7,
    29,
    17,
    0,
    tzinfo=timezone.utc,
)


def score_record(
    *,
    sample_id: str,
    split: str,
    label: int,
    score: float,
    defect_type: str,
) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "split": split,
        "label": label,
        "defect_type": defect_type,
        "anomaly_score": score,
        "has_mask": label == 1,
        "source_path": (f"{split}/{defect_type}/{sample_id}.png"),
    }


def create_score_payload() -> dict[str, object]:
    return {
        "schema_version": SCORE_ARTIFACT_SCHEMA_VERSION,
        "code_version": SCORE_ARTIFACT_CODE_VERSION,
        "random_seed": 42,
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
            score_record(
                sample_id="validation-001",
                split="validation",
                label=0,
                score=0.1,
                defect_type="good",
            ),
            score_record(
                sample_id="validation-002",
                split="validation",
                label=0,
                score=0.2,
                defect_type="good",
            ),
            score_record(
                sample_id="validation-003",
                split="validation",
                label=0,
                score=0.3,
                defect_type="good",
            ),
            score_record(
                sample_id="validation-004",
                split="validation",
                label=0,
                score=0.4,
                defect_type="good",
            ),
            score_record(
                sample_id="test-good-001",
                split="test",
                label=0,
                score=0.1,
                defect_type="good",
            ),
            score_record(
                sample_id="test-crack-001",
                split="test",
                label=1,
                score=0.3,
                defect_type="crack",
            ),
            score_record(
                sample_id="test-good-002",
                split="test",
                label=0,
                score=0.4,
                defect_type="good",
            ),
            score_record(
                sample_id="test-crack-002",
                split="test",
                label=1,
                score=0.8,
                defect_type="crack",
            ),
        ],
    }


def write_score_artifact(
    path: Path,
    payload: dict[str, object] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            payload or create_score_payload(),
            indent=2,
        ),
        encoding="utf-8",
    )


def test_complete_evaluation_preserves_train_validation_test_roles(
    tmp_path: Path,
) -> None:
    score_path = tmp_path / "scores.json"
    write_score_artifact(score_path)
    run_dir = tmp_path / "evaluations" / "run-001"

    artifact = generate_evaluation_run(
        score_artifact_path=score_path,
        run_dir=run_dir,
        threshold_quantile=0.5,
        created_at=FIXED_CREATED_AT,
    )

    assert artifact.evaluation.roc_auc == pytest.approx(0.75)
    assert artifact.evaluation.average_precision == (pytest.approx(5.0 / 6.0))
    assert artifact.evaluation.threshold_metrics.threshold == pytest.approx(0.25)

    metrics = json.loads(artifact.metrics_path.read_text(encoding="utf-8"))
    assert metrics["schema_version"] == (EVALUATION_SCHEMA_VERSION)
    assert metrics["code_version"] == (EVALUATION_CODE_VERSION)
    assert metrics["protocol"] == {
        "feature_bank_fit_split": "train",
        "threshold_selection_split": "validation",
        "evaluation_split": "test",
        "positive_class_label": 1,
        "positive_class_name": "anomalous",
        "higher_scores_mean": "more_anomalous",
        "prediction_rule": "score > threshold",
        "retune_after_test_evaluation": False,
    }
    assert metrics["feature_bank"]["split"] == "train"
    assert metrics["feature_extractor"]["pretrained_weights"] == "none"
    assert metrics["threshold_selection"]["validation_sample_count"] == 4
    assert metrics["metrics"]["sample_count"] == 4

    with artifact.sample_scores_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as sample_file:
        sample_rows = list(csv.DictReader(sample_file))

    assert [row["sample_id"] for row in sample_rows] == [
        "test-good-001",
        "test-crack-001",
        "test-good-002",
        "test-crack-002",
    ]
    assert {row["split"] for row in sample_rows} == {"test"}
    assert [row["predicted_label"] for row in sample_rows] == ["0", "1", "1", "1"]

    threshold = json.loads(artifact.threshold_path.read_text(encoding="utf-8"))
    assert threshold["calibration"]["split"] == ("validation")
    assert threshold["calibration"]["uses_test_scores"] is False

    config = json.loads(artifact.config_path.read_text(encoding="utf-8"))
    assert config["threshold_quantile"] == 0.5
    assert config["protocol"]["evaluation_split"] == "test"

    run_manifest = json.loads(artifact.run_manifest_path.read_text(encoding="utf-8"))
    assert run_manifest["run_name"] == "run-001"
    assert run_manifest["run_type"] == ("image_level_anomaly_evaluation")
    assert run_manifest["protocol"] == metrics["protocol"]
    assert run_manifest["effective_configuration"] == {
        "threshold_quantile": 0.5,
        "random_seed": 42,
        "scored_splits": [
            "validation",
            "test",
        ],
        "scorer": create_score_payload()["scorer"],
    }
    assert run_manifest["threshold_policy"]["calibration_split"] == "validation"
    assert run_manifest["threshold_policy"]["calibration_mode"] == "normal_only"
    assert run_manifest["lineage"]["dataset"] == (metrics["dataset"])
    assert run_manifest["lineage"]["feature_extractor"] == metrics["feature_extractor"]

    expected_manifest_artifacts = {
        "evaluation_config.json",
        "metrics.json",
        "sample_scores.csv",
        "threshold.json",
    }
    assert set(run_manifest["artifacts"]) == (expected_manifest_artifacts)
    for filename in expected_manifest_artifacts:
        artifact_path = artifact.run_dir / filename
        expected_sha256 = (
            "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        )
        assert run_manifest["artifacts"][filename] == {
            "path": filename,
            "sha256": expected_sha256,
        }

    assert sorted(path.name for path in artifact.run_dir.iterdir()) == [
        "evaluation_config.json",
        "metrics.json",
        RUN_MANIFEST_FILENAME,
        "sample_scores.csv",
        "threshold.json",
    ]


@pytest.mark.parametrize(
    "role_exchange",
    [
        "feature_bank",
        "records",
    ],
)
def test_exchanged_data_roles_are_rejected(
    tmp_path: Path,
    role_exchange: str,
) -> None:
    payload = create_score_payload()

    if role_exchange == "feature_bank":
        payload["feature_bank"]["split"] = "validation"
    else:
        payload["records"][0]["split"] = "train"

    score_path = tmp_path / f"{role_exchange}.json"
    write_score_artifact(score_path, payload)

    with pytest.raises(
        EvaluationRunError,
        match=(
            "training-only"
            if role_exchange == "feature_bank"
            else "validation and test"
        ),
    ):
        generate_evaluation_run(
            score_artifact_path=score_path,
            run_dir=tmp_path / "run",
            threshold_quantile=0.5,
            created_at=FIXED_CREATED_AT,
        )


def test_existing_run_requires_explicit_overwrite_policy(
    tmp_path: Path,
) -> None:
    score_path = tmp_path / "scores.json"
    write_score_artifact(score_path)
    run_dir = tmp_path / "run"

    generate_evaluation_run(
        score_artifact_path=score_path,
        run_dir=run_dir,
        threshold_quantile=0.5,
        created_at=FIXED_CREATED_AT,
    )

    with pytest.raises(
        EvaluationRunError,
        match="already exists",
    ):
        generate_evaluation_run(
            score_artifact_path=score_path,
            run_dir=run_dir,
            threshold_quantile=0.5,
            created_at=FIXED_CREATED_AT,
        )

    overwritten = generate_evaluation_run(
        score_artifact_path=score_path,
        run_dir=run_dir,
        threshold_quantile=0.5,
        existing_run_policy="overwrite",
        created_at=FIXED_CREATED_AT,
    )

    assert overwritten.metrics_path.is_file()
