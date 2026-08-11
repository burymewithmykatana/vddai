import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.tests.test_evaluate_baseline import (
    create_score_payload,
    write_score_artifact,
)
from ml.evaluate_baseline import generate_evaluation_run
from ml.experiment_tracking import (
    ExperimentTracker,
    ExperimentTrackingError,
    TrackedArtifact,
)
from ml.track_baseline_experiment import (
    BASELINE_EXPERIMENT_NAME,
    BaselineTrackingError,
    prepare_baseline_experiment,
    record_baseline_experiment,
)

FIXED_TIME = datetime(2026, 8, 12, 9, 30, tzinfo=timezone.utc)
CODE_REVISION = "a" * 40


def sha256_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def start_test_run(tracker: ExperimentTracker, run_id: str) -> None:
    tracker.start_run(
        run_id=run_id,
        experiment_name="test-experiment",
        dataset_name="MVTec AD",
        dataset_category="tile",
        dataset_version="dataset-v1",
        manifest_fingerprint="sha256:" + "1" * 64,
        code_revision=CODE_REVISION,
        parameters={"scorer.k": 1, "threshold.quantile": 0.95},
        started_at=FIXED_TIME,
    )


def test_completed_experiment_is_queryable_and_immutable(tmp_path: Path) -> None:
    tracker = ExperimentTracker(tmp_path / "experiments.sqlite3")
    start_test_run(tracker, "run-001")

    tracker.complete_run(
        "run-001",
        metrics={"roc_auc": 0.96, "threshold.f1": 0.94},
        artifacts=[
            TrackedArtifact(
                name="evaluation.metrics",
                path="artifacts/evaluations/run-001/metrics.json",
                sha256="sha256:" + "2" * 64,
                schema_version="metrics.v1",
                code_version="metrics.generator.v1",
            )
        ],
        completed_at=FIXED_TIME,
    )

    run = tracker.get_run("run-001")
    assert run["status"] == "completed"
    assert run["parameters"] == {
        "scorer.k": 1,
        "threshold.quantile": 0.95,
    }
    assert run["metrics"] == {
        "roc_auc": 0.96,
        "threshold.f1": 0.94,
    }
    assert run["artifacts"][0]["path"] == ("artifacts/evaluations/run-001/metrics.json")
    assert [item["run_id"] for item in tracker.list_runs(status="completed")] == [
        "run-001"
    ]

    with pytest.raises(ExperimentTrackingError, match="already terminal"):
        tracker.complete_run("run-001", metrics={}, artifacts=[])
    with pytest.raises(ExperimentTrackingError, match="already exists"):
        start_test_run(tracker, "run-001")


def test_failed_experiment_remains_terminal_evidence(tmp_path: Path) -> None:
    tracker = ExperimentTracker(tmp_path / "experiments.sqlite3")
    start_test_run(tracker, "run-failed")

    tracker.fail_run(
        "run-failed",
        failure_reason="artifact checksum mismatch",
        completed_at=FIXED_TIME,
    )

    failed = tracker.get_run("run-failed")
    assert failed["status"] == "failed"
    assert failed["failure_reason"] == "artifact checksum mismatch"
    assert failed["metrics"] == {}
    assert failed["artifacts"] == []
    with pytest.raises(ExperimentTrackingError, match="already terminal"):
        tracker.complete_run("run-failed", metrics={}, artifacts=[])


def build_baseline_artifacts(project_root: Path) -> tuple[Path, Path, Path]:
    feature_bank_dir = project_root / "artifacts" / "feature_banks" / "baseline"
    feature_bank_dir.mkdir(parents=True)
    feature_bytes = b"deterministic-feature-bank-fixture"
    feature_path = feature_bank_dir / "features.npz"
    feature_path.write_bytes(feature_bytes)
    feature_sha256 = sha256_bytes(feature_bytes)

    score_payload = create_score_payload()
    score_payload["dataset"]["manifest_fingerprint"] = "sha256:" + "3" * 64
    score_payload["feature_bank"]["features_sha256"] = feature_sha256
    score_path = project_root / "artifacts" / "anomaly_scores" / "scores.json"
    score_path.parent.mkdir(parents=True)
    write_score_artifact(score_path, score_payload)

    dataset = score_payload["dataset"]
    feature_metadata = {
        "schema_version": score_payload["feature_bank"]["schema_version"],
        "code_version": score_payload["feature_bank"]["code_version"],
        "dataset_version": dataset["version"],
        "manifest_fingerprint": dataset["manifest_fingerprint"],
        "split": "train",
        "sample_count": score_payload["feature_bank"]["sample_count"],
        "random_seed": score_payload["random_seed"],
        "feature_extractor": score_payload["feature_extractor"],
        "files": {
            "features": {
                "path": feature_path.name,
                "sha256": feature_sha256,
            }
        },
    }
    (feature_bank_dir / "metadata.json").write_text(
        json.dumps(feature_metadata),
        encoding="utf-8",
    )

    evaluation_run_dir = project_root / "artifacts" / "evaluations" / "baseline"
    generate_evaluation_run(
        score_artifact_path=score_path,
        run_dir=evaluation_run_dir,
        threshold_quantile=0.5,
        created_at=FIXED_TIME,
    )
    return evaluation_run_dir, score_path, feature_bank_dir


def test_week4_baseline_artifacts_form_complete_tracked_run(tmp_path: Path) -> None:
    evaluation_run_dir, score_path, feature_bank_dir = build_baseline_artifacts(
        tmp_path
    )
    tracker_path = tmp_path / "artifacts" / "experiments" / "runs.sqlite3"

    run = record_baseline_experiment(
        tracker_path=tracker_path,
        run_id="week4-baseline",
        code_revision=CODE_REVISION,
        evaluation_run_dir=evaluation_run_dir,
        score_artifact_path=score_path,
        feature_bank_dir=feature_bank_dir,
        project_root=tmp_path,
    )

    assert run["experiment_name"] == BASELINE_EXPERIMENT_NAME
    assert run["status"] == "completed"
    assert run["dataset_version"] == "fake-dataset-v1"
    assert run["manifest_fingerprint"] == "sha256:" + "3" * 64
    assert run["code_revision"] == CODE_REVISION
    assert run["parameters"]["feature_extractor.name"] == "test.fake"
    assert run["parameters"]["scorer.k"] == 1
    assert run["parameters"]["threshold.quantile"] == 0.5
    assert run["parameters"]["random_seed"] == 42
    assert run["metrics"]["roc_auc"] == pytest.approx(0.75)
    assert run["metrics"]["average_precision"] == pytest.approx(5.0 / 6.0)
    artifact_names = {artifact["name"] for artifact in run["artifacts"]}
    assert artifact_names == {
        "evaluation.evaluation_config.json",
        "evaluation.metrics.json",
        "evaluation.run_manifest",
        "evaluation.sample_scores.csv",
        "evaluation.threshold.json",
        "feature_bank.features",
        "feature_bank.metadata",
        "scores.validation_and_test",
    }


def test_tampered_evaluation_artifact_is_not_tracked(tmp_path: Path) -> None:
    evaluation_run_dir, score_path, feature_bank_dir = build_baseline_artifacts(
        tmp_path
    )
    (evaluation_run_dir / "sample_scores.csv").write_text(
        "tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(BaselineTrackingError, match="checksum mismatch"):
        prepare_baseline_experiment(
            evaluation_run_dir=evaluation_run_dir,
            score_artifact_path=score_path,
            feature_bank_dir=feature_bank_dir,
            project_root=tmp_path,
        )
