"""Validate and track the frozen Week 4 baseline evaluation as one run."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from ml.data.mvtec_contract import PROJECT_ROOT
from ml.evaluate_baseline import (
    DEFAULT_EVALUATION_ROOT,
    EVALUATION_CODE_VERSION,
    EVALUATION_SCHEMA_VERSION,
)
from ml.experiment_tracking import (
    DEFAULT_EXPERIMENT_TRACKER_PATH,
    ExperimentTracker,
    ExperimentTrackingError,
    TrackedArtifact,
)
from ml.generate_feature_bank import DEFAULT_ARTIFACT_DIR as DEFAULT_FEATURE_BANK_DIR
from ml.score_anomalies import DEFAULT_SCORE_ARTIFACT_DIR, SCORES_FILENAME

BASELINE_EXPERIMENT_NAME = "mvtec-ad-tile-resnet18-knn-baseline"
DEFAULT_BASELINE_RUN_DIR = DEFAULT_EVALUATION_ROOT / "baseline_q95_20260729"


class BaselineTrackingError(RuntimeError):
    """Raised when baseline artifacts cannot form an auditable experiment."""


@dataclass(frozen=True)
class BaselineExperiment:
    dataset: dict[str, object]
    parameters: dict[str, object]
    metrics: dict[str, float | int]
    artifacts: tuple[TrackedArtifact, ...]
    started_at: datetime


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineTrackingError(f"{label} could not be loaded.") from exc
    if not isinstance(payload, dict):
        raise BaselineTrackingError(f"{label} must be a JSON object.")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as artifact_file:
            for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise BaselineTrackingError(f"Artifact is unavailable: {path}") from exc
    return f"sha256:{digest.hexdigest()}"


def _project_relative(path: Path, *, project_root: Path) -> str:
    resolved_root = project_root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise BaselineTrackingError(
            "Tracked artifacts must be located under the project root."
        ) from exc


def _artifact_member(root: Path, relative_path: str, *, label: str) -> Path:
    portable_path = PurePosixPath(relative_path.replace("\\", "/"))
    if (
        portable_path.is_absolute()
        or PureWindowsPath(relative_path).is_absolute()
        or ".." in portable_path.parts
        or ".." in PureWindowsPath(relative_path).parts
    ):
        raise BaselineTrackingError(f"{label} path must be package-relative.")
    resolved_root = root.resolve()
    candidate = (resolved_root / Path(*portable_path.parts)).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise BaselineTrackingError(f"{label} path escapes its artifact root.") from exc
    return candidate


def _parse_utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise BaselineTrackingError("Evaluation timestamp must be canonical UTC.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BaselineTrackingError("Evaluation timestamp is invalid.") from exc


def _verified_artifact(
    *,
    name: str,
    path: Path,
    expected_sha256: str,
    project_root: Path,
    schema_version: str | None,
    code_version: str | None,
) -> TrackedArtifact:
    actual_sha256 = _sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise BaselineTrackingError(f"Artifact checksum mismatch for {name}.")
    return TrackedArtifact(
        name=name,
        path=_project_relative(path, project_root=project_root),
        sha256=actual_sha256,
        schema_version=schema_version,
        code_version=code_version,
    )


def _validate_protocol(protocol: object) -> None:
    expected = {
        "feature_bank_fit_split": "train",
        "threshold_selection_split": "validation",
        "evaluation_split": "test",
        "positive_class_label": 1,
        "positive_class_name": "anomalous",
        "higher_scores_mean": "more_anomalous",
        "prediction_rule": "score > threshold",
        "retune_after_test_evaluation": False,
    }
    if protocol != expected:
        raise BaselineTrackingError("Evaluation protocol is not the frozen baseline.")


def prepare_baseline_experiment(
    *,
    evaluation_run_dir: Path,
    score_artifact_path: Path,
    feature_bank_dir: Path,
    project_root: Path = PROJECT_ROOT,
) -> BaselineExperiment:
    run_dir = evaluation_run_dir.resolve()
    manifest_path = run_dir / "run_manifest.json"
    metrics_path = run_dir / "metrics.json"
    manifest = _load_json_object(manifest_path, label="Run manifest")
    metrics_payload = _load_json_object(metrics_path, label="Evaluation metrics")
    feature_metadata_path = feature_bank_dir.resolve() / "metadata.json"
    feature_metadata = _load_json_object(
        feature_metadata_path,
        label="Feature-bank metadata",
    )

    if manifest.get("schema_version") != EVALUATION_SCHEMA_VERSION:
        raise BaselineTrackingError("Unsupported evaluation manifest schema.")
    if manifest.get("code_version") != EVALUATION_CODE_VERSION:
        raise BaselineTrackingError("Unsupported evaluation manifest code version.")
    if manifest.get("run_type") != "image_level_anomaly_evaluation":
        raise BaselineTrackingError("Run manifest is not an image evaluation.")
    _validate_protocol(manifest.get("protocol"))
    if metrics_payload.get("protocol") != manifest.get("protocol"):
        raise BaselineTrackingError("Metrics and run manifest protocols differ.")

    lineage = manifest.get("lineage")
    if not isinstance(lineage, dict):
        raise BaselineTrackingError("Run manifest lineage is incomplete.")
    dataset = lineage.get("dataset")
    feature_bank = lineage.get("feature_bank")
    feature_extractor = lineage.get("feature_extractor")
    source_scores = lineage.get("source_scores")
    if not all(
        isinstance(value, dict)
        for value in (dataset, feature_bank, feature_extractor, source_scores)
    ):
        raise BaselineTrackingError("Run manifest lineage is incomplete.")
    if metrics_payload.get("dataset") != dataset:
        raise BaselineTrackingError("Metrics dataset lineage differs from manifest.")
    if metrics_payload.get("feature_extractor") != feature_extractor:
        raise BaselineTrackingError("Feature-extractor lineage differs from metrics.")
    required_dataset_fields = ("name", "category", "version", "manifest_fingerprint")
    if any(
        not isinstance(dataset.get(field), str) or not dataset[field].strip()
        for field in required_dataset_fields
    ):
        raise BaselineTrackingError("Dataset lineage is incomplete.")
    if (
        not isinstance(feature_extractor.get("name"), str)
        or not isinstance(feature_extractor.get("pretrained_weights"), str)
        or not isinstance(feature_extractor.get("feature_layer"), str)
        or not isinstance(feature_extractor.get("feature_dimension"), int)
        or feature_extractor["feature_dimension"] <= 0
        or not isinstance(feature_extractor.get("normalization"), dict)
    ):
        raise BaselineTrackingError("Feature-extractor lineage is incomplete.")
    if feature_metadata.get("dataset_version") != dataset.get("version"):
        raise BaselineTrackingError("Feature-bank dataset version is inconsistent.")
    if feature_metadata.get("manifest_fingerprint") != dataset.get(
        "manifest_fingerprint"
    ):
        raise BaselineTrackingError(
            "Feature-bank manifest fingerprint is inconsistent."
        )
    if feature_metadata.get("feature_extractor") != feature_extractor:
        raise BaselineTrackingError("Feature-bank extractor lineage is inconsistent.")
    if feature_metadata.get("split") != "train":
        raise BaselineTrackingError("Feature bank must contain training records only.")

    run_artifacts = manifest.get("artifacts")
    if not isinstance(run_artifacts, dict) or not run_artifacts:
        raise BaselineTrackingError("Run manifest artifact inventory is incomplete.")
    artifacts: list[TrackedArtifact] = []
    for filename, descriptor in sorted(run_artifacts.items()):
        if not isinstance(filename, str) or not isinstance(descriptor, dict):
            raise BaselineTrackingError("Run artifact descriptor is invalid.")
        relative_path = descriptor.get("path")
        expected_sha256 = descriptor.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_sha256, str):
            raise BaselineTrackingError("Run artifact descriptor is incomplete.")
        candidate = _artifact_member(
            run_dir,
            relative_path,
            label="Run artifact",
        )
        artifacts.append(
            _verified_artifact(
                name=f"evaluation.{filename}",
                path=candidate,
                expected_sha256=expected_sha256,
                project_root=project_root,
                schema_version=EVALUATION_SCHEMA_VERSION,
                code_version=EVALUATION_CODE_VERSION,
            )
        )

    artifacts.append(
        TrackedArtifact(
            name="evaluation.run_manifest",
            path=_project_relative(manifest_path, project_root=project_root),
            sha256=_sha256_file(manifest_path),
            schema_version=EVALUATION_SCHEMA_VERSION,
            code_version=EVALUATION_CODE_VERSION,
        )
    )
    score_checksum = source_scores.get("sha256")
    if not isinstance(score_checksum, str):
        raise BaselineTrackingError("Source-score checksum is missing.")
    artifacts.append(
        _verified_artifact(
            name="scores.validation_and_test",
            path=score_artifact_path.resolve(),
            expected_sha256=score_checksum,
            project_root=project_root,
            schema_version=source_scores.get("schema_version"),
            code_version=source_scores.get("code_version"),
        )
    )

    feature_files = feature_metadata.get("files")
    feature_descriptor = (
        feature_files.get("features") if isinstance(feature_files, dict) else None
    )
    if not isinstance(feature_descriptor, dict):
        raise BaselineTrackingError("Feature-bank artifact descriptor is missing.")
    feature_relative_path = feature_descriptor.get("path")
    feature_checksum = feature_descriptor.get("sha256")
    if not isinstance(feature_relative_path, str) or not isinstance(
        feature_checksum, str
    ):
        raise BaselineTrackingError("Feature-bank artifact descriptor is incomplete.")
    if feature_checksum != feature_bank.get("features_sha256"):
        raise BaselineTrackingError("Feature-bank checksum lineage is inconsistent.")
    artifacts.extend(
        (
            _verified_artifact(
                name="feature_bank.features",
                path=_artifact_member(
                    feature_bank_dir,
                    feature_relative_path,
                    label="Feature-bank artifact",
                ),
                expected_sha256=feature_checksum,
                project_root=project_root,
                schema_version=feature_metadata.get("schema_version"),
                code_version=feature_metadata.get("code_version"),
            ),
            TrackedArtifact(
                name="feature_bank.metadata",
                path=_project_relative(
                    feature_metadata_path,
                    project_root=project_root,
                ),
                sha256=_sha256_file(feature_metadata_path),
                schema_version=feature_metadata.get("schema_version"),
                code_version=feature_metadata.get("code_version"),
            ),
        )
    )

    effective_configuration = manifest.get("effective_configuration")
    threshold_policy = manifest.get("threshold_policy")
    if not isinstance(effective_configuration, dict) or not isinstance(
        threshold_policy, dict
    ):
        raise BaselineTrackingError("Effective baseline configuration is incomplete.")
    scorer = effective_configuration.get("scorer")
    if not isinstance(scorer, dict):
        raise BaselineTrackingError("Scorer configuration is incomplete.")
    evaluation_metrics = metrics_payload.get("metrics")
    if not isinstance(evaluation_metrics, dict):
        raise BaselineTrackingError("Evaluation metric payload is incomplete.")
    threshold_metrics = evaluation_metrics.get("threshold_metrics")
    if not isinstance(threshold_metrics, dict):
        raise BaselineTrackingError("Threshold metrics are incomplete.")

    parameters = {
        "feature_extractor.name": feature_extractor.get("name"),
        "feature_extractor.pretrained_weights": feature_extractor.get(
            "pretrained_weights"
        ),
        "feature_extractor.feature_layer": feature_extractor.get("feature_layer"),
        "feature_extractor.feature_dimension": feature_extractor.get(
            "feature_dimension"
        ),
        "feature_extractor.normalization": feature_extractor.get("normalization"),
        "scorer.distance": scorer.get("distance"),
        "scorer.aggregation": scorer.get("aggregation"),
        "scorer.k": scorer.get("k"),
        "threshold.policy": threshold_policy.get("name"),
        "threshold.quantile": threshold_policy.get("quantile"),
        "threshold.value": threshold_policy.get("threshold"),
        "random_seed": effective_configuration.get("random_seed"),
        "evaluation.protocol": manifest.get("protocol"),
    }
    tracked_metrics = {
        "roc_auc": evaluation_metrics["roc_auc"],
        "average_precision": evaluation_metrics["average_precision"],
        "sample_count": evaluation_metrics["sample_count"],
        "threshold.accuracy": threshold_metrics["accuracy"],
        "threshold.f1": threshold_metrics["f1"],
        "threshold.precision": threshold_metrics["precision"],
        "threshold.recall": threshold_metrics["recall"],
        "threshold.specificity": threshold_metrics["specificity"],
        "threshold.false_positive_rate": threshold_metrics["false_positive_rate"],
        "threshold.false_negative_rate": threshold_metrics["false_negative_rate"],
    }
    return BaselineExperiment(
        dataset=dataset,
        parameters=parameters,
        metrics=tracked_metrics,
        artifacts=tuple(artifacts),
        started_at=_parse_utc_timestamp(manifest.get("created_at")),
    )


def resolve_clean_git_revision(project_root: Path = PROJECT_ROOT) -> str:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BaselineTrackingError("Git code revision could not be resolved.") from exc
    if status.stdout.strip():
        raise BaselineTrackingError(
            "Refusing to track an ambiguous dirty code revision; commit first."
        )
    if len(revision) != 40:
        raise BaselineTrackingError("Git code revision is not a full commit SHA.")
    return revision


def record_baseline_experiment(
    *,
    tracker_path: Path,
    run_id: str,
    code_revision: str,
    evaluation_run_dir: Path,
    score_artifact_path: Path,
    feature_bank_dir: Path,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, object]:
    prepared = prepare_baseline_experiment(
        evaluation_run_dir=evaluation_run_dir,
        score_artifact_path=score_artifact_path,
        feature_bank_dir=feature_bank_dir,
        project_root=project_root,
    )
    dataset = prepared.dataset
    tracker = ExperimentTracker(tracker_path)
    tracker.start_run(
        run_id=run_id,
        experiment_name=BASELINE_EXPERIMENT_NAME,
        dataset_name=str(dataset.get("name", "")),
        dataset_category=str(dataset.get("category", "")),
        dataset_version=str(dataset.get("version", "")),
        manifest_fingerprint=str(dataset.get("manifest_fingerprint", "")),
        code_revision=code_revision,
        parameters=prepared.parameters,
        started_at=prepared.started_at,
    )
    try:
        tracker.complete_run(
            run_id,
            metrics=prepared.metrics,
            artifacts=prepared.artifacts,
            completed_at=prepared.started_at,
        )
    except ExperimentTrackingError as exc:
        tracker.fail_run(
            run_id,
            failure_reason=f"Experiment completion validation failed: {exc}",
        )
        raise
    return tracker.get_run(run_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Track the frozen Week 4 baseline in the local experiment ledger."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tracker", type=Path, default=DEFAULT_EXPERIMENT_TRACKER_PATH)
    parser.add_argument(
        "--evaluation-run-dir",
        type=Path,
        default=DEFAULT_BASELINE_RUN_DIR,
    )
    parser.add_argument(
        "--scores",
        type=Path,
        default=DEFAULT_SCORE_ARTIFACT_DIR / SCORES_FILENAME,
    )
    parser.add_argument(
        "--feature-bank-dir",
        type=Path,
        default=DEFAULT_FEATURE_BANK_DIR,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = record_baseline_experiment(
            tracker_path=args.tracker,
            run_id=args.run_id,
            code_revision=resolve_clean_git_revision(),
            evaluation_run_dir=args.evaluation_run_dir,
            score_artifact_path=args.scores,
            feature_bank_dir=args.feature_bank_dir,
        )
    except (BaselineTrackingError, ExperimentTrackingError) as exc:
        raise SystemExit(f"Baseline experiment was not tracked: {exc}") from exc
    print("Baseline experiment tracked")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
