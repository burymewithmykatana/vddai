"""Produce a complete image-level anomaly baseline evaluation run.

Run with ``python -m ml.evaluate_baseline``. The command freezes its method
before inspecting official-test metrics: training-bank lineage must be
``train``, threshold calibration uses ``validation`` only, and metric
calculation uses ``test`` only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np

from ml.data.mvtec_contract import PROJECT_ROOT
from ml.evaluation import (
    EvaluationError,
    ImageLevelEvaluation,
    evaluate_image_level_scores,
    threshold_predictions,
)
from ml.score_anomalies import (
    DEFAULT_SCORE_ARTIFACT_DIR,
    SCORES_FILENAME,
    SCORE_ARTIFACT_SCHEMA_VERSION,
)
from ml.select_threshold import (
    DEFAULT_QUANTILE,
    THRESHOLD_FILENAME,
    ThresholdArtifactError,
    select_threshold_artifact,
)

EVALUATION_SCHEMA_VERSION = "vddai.image_evaluation.v1"
EVALUATION_CODE_VERSION = "vddai.image_evaluation.generator.v1"
METRICS_FILENAME = "metrics.json"
SAMPLE_SCORES_FILENAME = "sample_scores.csv"
CONFIG_FILENAME = "evaluation_config.json"
RUN_MANIFEST_FILENAME = "run_manifest.json"
DEFAULT_EVALUATION_ROOT = PROJECT_ROOT / "artifacts" / "evaluations"

ExistingRunPolicy = Literal["error", "overwrite"]


class EvaluationRunError(RuntimeError):
    """Raised when a protocol-safe evaluation run cannot be produced."""


@dataclass(frozen=True)
class EvaluationRunArtifacts:
    run_dir: Path
    metrics_path: Path
    sample_scores_path: Path
    threshold_path: Path
    config_path: Path
    run_manifest_path: Path
    evaluation: ImageLevelEvaluation


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source_file:
        for chunk in iter(
            lambda: source_file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return f"sha256:{digest.hexdigest()}"


def _write_json(
    output_path: Path,
    payload: dict[str, object],
) -> None:
    with output_path.open(
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            payload,
            output_file,
            indent=2,
            sort_keys=True,
        )
        output_file.write("\n")
        output_file.flush()
        os.fsync(output_file.fileno())


def _write_sample_scores(
    *,
    output_path: Path,
    test_records: list[dict[str, object]],
    predictions: np.ndarray,
) -> None:
    fieldnames = [
        "sample_id",
        "split",
        "label",
        "defect_type",
        "anomaly_score",
        "has_mask",
        "source_path",
        "predicted_label",
        "predicted_class",
    ]

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=fieldnames,
        )
        writer.writeheader()

        for record, prediction in zip(
            test_records,
            predictions,
            strict=True,
        ):
            writer.writerow(
                {
                    "sample_id": record["sample_id"],
                    "split": record["split"],
                    "label": record["label"],
                    "defect_type": record["defect_type"],
                    "anomaly_score": record["anomaly_score"],
                    "has_mask": record["has_mask"],
                    "source_path": record["source_path"],
                    "predicted_label": int(prediction),
                    "predicted_class": ("anomalous" if prediction else "normal"),
                }
            )

        output_file.flush()
        os.fsync(output_file.fileno())


def _load_and_validate_score_artifact(
    score_artifact_path: Path,
) -> dict[str, object]:
    try:
        payload = json.loads(score_artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationRunError("Score artifact could not be loaded.") from exc

    if not isinstance(payload, dict):
        raise EvaluationRunError("Score artifact must be a JSON object.")

    if payload.get("schema_version") != (SCORE_ARTIFACT_SCHEMA_VERSION):
        raise EvaluationRunError("Unsupported score-artifact schema version.")

    lineage_keys = (
        "dataset",
        "feature_bank",
        "feature_extractor",
        "scorer",
        "records",
    )
    if any(key not in payload for key in lineage_keys):
        raise EvaluationRunError("Score artifact lineage is incomplete.")

    feature_bank = payload["feature_bank"]
    if not isinstance(feature_bank, dict) or feature_bank.get("split") != "train":
        raise EvaluationRunError("Evaluation requires a training-only feature bank.")

    scorer = payload["scorer"]
    if (
        not isinstance(scorer, dict)
        or scorer.get("higher_is_more_anomalous") is not True
    ):
        raise EvaluationRunError(
            "Evaluation requires higher scores to mean more anomalous."
        )

    records = payload["records"]
    if (
        not isinstance(records, list)
        or not records
        or not all(isinstance(record, dict) for record in records)
    ):
        raise EvaluationRunError(
            "Score artifact records must be a non-empty JSON array."
        )

    required_record_keys = {
        "sample_id",
        "split",
        "label",
        "defect_type",
        "anomaly_score",
        "has_mask",
        "source_path",
    }
    if any(not required_record_keys.issubset(record) for record in records):
        raise EvaluationRunError("Score records do not match the expected schema.")

    sample_ids = [record["sample_id"] for record in records]
    if len(set(sample_ids)) != len(sample_ids):
        raise EvaluationRunError("Score record sample IDs must be unique.")

    split_names = {record["split"] for record in records}
    if split_names != {"validation", "test"}:
        raise EvaluationRunError(
            "Score records must contain validation and test splits only."
        )

    return payload


def _publish_staged_run(
    *,
    stage_dir: Path,
    run_dir: Path,
    existing_run_policy: ExistingRunPolicy,
) -> None:
    if not run_dir.exists():
        os.replace(stage_dir, run_dir)
        return

    if existing_run_policy != "overwrite":
        raise EvaluationRunError("Evaluation run already exists.")

    if not run_dir.is_dir():
        raise EvaluationRunError("Evaluation run path exists and is not a directory.")

    for filename in (
        METRICS_FILENAME,
        SAMPLE_SCORES_FILENAME,
        THRESHOLD_FILENAME,
        CONFIG_FILENAME,
        RUN_MANIFEST_FILENAME,
    ):
        os.replace(
            stage_dir / filename,
            run_dir / filename,
        )

    stage_dir.rmdir()


def generate_evaluation_run(
    *,
    score_artifact_path: Path,
    run_dir: Path,
    threshold_quantile: float = DEFAULT_QUANTILE,
    existing_run_policy: ExistingRunPolicy = "error",
    created_at: datetime | None = None,
) -> EvaluationRunArtifacts:
    """Select on validation, evaluate test once, and persist one run."""
    if existing_run_policy not in {
        "error",
        "overwrite",
    }:
        raise EvaluationRunError("Existing-run policy must be error or overwrite.")

    run_dir = run_dir.resolve()
    if run_dir.exists() and existing_run_policy == "error":
        raise EvaluationRunError("Evaluation run already exists.")

    score_payload = _load_and_validate_score_artifact(score_artifact_path)
    records = score_payload["records"]
    test_records = [record for record in records if record["split"] == "test"]

    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise EvaluationRunError(
            "Creation timestamp must include timezone information."
        )
    created_at_utc = (
        timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    run_dir.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(
        tempfile.mkdtemp(
            dir=run_dir.parent,
            prefix=f".{run_dir.name}.",
        )
    )

    try:
        threshold_artifact = select_threshold_artifact(
            score_artifact_path=score_artifact_path,
            artifact_dir=stage_dir,
            quantile=threshold_quantile,
            created_at=timestamp,
        )
        threshold = threshold_artifact.selection.threshold

        test_scores = [record["anomaly_score"] for record in test_records]
        test_labels = [record["label"] for record in test_records]
        defect_types = [record["defect_type"] for record in test_records]

        try:
            evaluation = evaluate_image_level_scores(
                test_scores=test_scores,
                test_labels=test_labels,
                defect_types=defect_types,
                threshold=threshold,
            )
        except EvaluationError as exc:
            raise EvaluationRunError(
                "Official-test records cannot support evaluation."
            ) from exc

        predictions = threshold_predictions(
            scores=test_scores,
            threshold=threshold,
        )

        protocol = {
            "feature_bank_fit_split": "train",
            "threshold_selection_split": "validation",
            "evaluation_split": "test",
            "positive_class_label": 1,
            "positive_class_name": "anomalous",
            "higher_scores_mean": "more_anomalous",
            "prediction_rule": "score > threshold",
            "retune_after_test_evaluation": False,
        }
        source_scores = {
            "schema_version": score_payload["schema_version"],
            "code_version": score_payload.get("code_version"),
            "sha256": _sha256_file(score_artifact_path),
        }
        config_payload: dict[str, object] = {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "code_version": EVALUATION_CODE_VERSION,
            "created_at": created_at_utc,
            "threshold_quantile": threshold_quantile,
            "existing_run_policy": existing_run_policy,
            "protocol": protocol,
            "source_scores": source_scores,
        }
        metrics_payload: dict[str, object] = {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "code_version": EVALUATION_CODE_VERSION,
            "created_at": created_at_utc,
            "protocol": protocol,
            "dataset": score_payload["dataset"],
            "feature_bank": score_payload["feature_bank"],
            "feature_extractor": score_payload["feature_extractor"],
            "scorer": score_payload["scorer"],
            "threshold_selection": asdict(threshold_artifact.selection),
            "metrics": asdict(evaluation),
            "source_scores": source_scores,
        }

        _write_json(
            stage_dir / METRICS_FILENAME,
            metrics_payload,
        )
        _write_json(
            stage_dir / CONFIG_FILENAME,
            config_payload,
        )
        _write_sample_scores(
            output_path=(stage_dir / SAMPLE_SCORES_FILENAME),
            test_records=test_records,
            predictions=predictions,
        )
        artifact_files = {
            filename: {
                "path": filename,
                "sha256": _sha256_file(stage_dir / filename),
            }
            for filename in (
                METRICS_FILENAME,
                SAMPLE_SCORES_FILENAME,
                THRESHOLD_FILENAME,
                CONFIG_FILENAME,
            )
        }
        run_manifest_payload: dict[str, object] = {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "code_version": EVALUATION_CODE_VERSION,
            "created_at": created_at_utc,
            "run_name": run_dir.name,
            "run_type": "image_level_anomaly_evaluation",
            "protocol": protocol,
            "effective_configuration": {
                "threshold_quantile": threshold_quantile,
                "random_seed": score_payload.get("random_seed"),
                "scored_splits": score_payload.get(
                    "splits",
                    ["validation", "test"],
                ),
                "scorer": score_payload["scorer"],
            },
            "threshold_policy": {
                "name": (threshold_artifact.selection.threshold_policy),
                "quantile": (threshold_artifact.selection.quantile),
                "threshold": threshold,
                "calibration_split": "validation",
                "calibration_mode": "normal_only",
            },
            "lineage": {
                "dataset": score_payload["dataset"],
                "feature_bank": score_payload["feature_bank"],
                "feature_extractor": score_payload["feature_extractor"],
                "source_scores": source_scores,
            },
            "artifacts": artifact_files,
        }
        _write_json(
            stage_dir / RUN_MANIFEST_FILENAME,
            run_manifest_payload,
        )

        _publish_staged_run(
            stage_dir=stage_dir,
            run_dir=run_dir,
            existing_run_policy=existing_run_policy,
        )
    except (
        EvaluationRunError,
        ThresholdArtifactError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        if stage_dir.exists():
            shutil.rmtree(stage_dir)

        if isinstance(exc, EvaluationRunError):
            raise

        raise EvaluationRunError("Evaluation run could not be completed.") from exc

    return EvaluationRunArtifacts(
        run_dir=run_dir,
        metrics_path=run_dir / METRICS_FILENAME,
        sample_scores_path=(run_dir / SAMPLE_SCORES_FILENAME),
        threshold_path=run_dir / THRESHOLD_FILENAME,
        config_path=run_dir / CONFIG_FILENAME,
        run_manifest_path=(run_dir / RUN_MANIFEST_FILENAME),
        evaluation=evaluation,
    )


def _default_run_name(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).strftime("run_%Y%m%dT%H%M%S%fZ")


def _resolve_run_dir(
    *,
    output_root: Path,
    run_name: str,
) -> Path:
    root = output_root.resolve()
    candidate = Path(run_name)

    if candidate.is_absolute():
        raise EvaluationRunError("Run name must be relative.")

    run_dir = (root / candidate).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise EvaluationRunError(
            "Run name escapes the evaluation artifact root."
        ) from exc

    return run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Evaluate the frozen image-level anomaly baseline once.")
    )
    parser.add_argument(
        "--scores",
        type=Path,
        default=(DEFAULT_SCORE_ARTIFACT_DIR / SCORES_FILENAME),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_EVALUATION_ROOT,
    )
    parser.add_argument(
        "--run-name",
        default=None,
    )
    parser.add_argument(
        "--threshold-quantile",
        type=float,
        default=DEFAULT_QUANTILE,
    )
    parser.add_argument(
        "--existing-run-policy",
        choices=("error", "overwrite"),
        default="error",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = datetime.now(timezone.utc)
    run_name = (
        args.run_name if args.run_name is not None else _default_run_name(timestamp)
    )
    run_dir = _resolve_run_dir(
        output_root=args.output_root,
        run_name=run_name,
    )
    artifact = generate_evaluation_run(
        score_artifact_path=args.scores,
        run_dir=run_dir,
        threshold_quantile=args.threshold_quantile,
        existing_run_policy=args.existing_run_policy,
        created_at=timestamp,
    )

    metrics = artifact.evaluation
    print("Image-level anomaly evaluation completed")
    print(f"Run: {artifact.run_dir}")
    print(f"ROC-AUC: {metrics.roc_auc}")
    print(f"Average precision: {metrics.average_precision}")
    print("F1 at validation threshold: " f"{metrics.threshold_metrics.f1}")
    print(f"Metrics: {artifact.metrics_path}")
    print(f"Sample scores: {artifact.sample_scores_path}")


if __name__ == "__main__":
    main()
