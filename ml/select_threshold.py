"""Create a validation-only threshold artifact.

Run with ``python -m ml.select_threshold``. The command reads validation
records from the anomaly-score artifact and never passes test records or test
labels into threshold selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ml.data.mvtec_contract import PROJECT_ROOT
from ml.score_anomalies import (
    DEFAULT_SCORE_ARTIFACT_DIR,
    SCORES_FILENAME,
    SCORE_ARTIFACT_SCHEMA_VERSION,
)
from ml.threshold_selector import (
    QUANTILE_METHOD,
    NormalValidationQuantileThresholdSelector,
    ThresholdSelection,
    ThresholdSelectionError,
)

THRESHOLD_ARTIFACT_SCHEMA_VERSION = "vddai.threshold.v1"
THRESHOLD_ARTIFACT_CODE_VERSION = "vddai.threshold.generator.v1"
THRESHOLD_FILENAME = "threshold.json"
DEFAULT_QUANTILE = 0.95
DEFAULT_THRESHOLD_ARTIFACT_DIR = (
    PROJECT_ROOT
    / "artifacts"
    / "thresholds"
    / "mvtec_ad_tile_resnet18_knn_normal_quantile"
)


class ThresholdArtifactError(RuntimeError):
    """Raised when a threshold artifact cannot be selected safely."""


@dataclass(frozen=True)
class ThresholdArtifact:
    """Completed threshold artifact and selection result."""

    artifact_dir: Path
    threshold_path: Path
    selection: ThresholdSelection


def _validation_records_fingerprint(
    validation_records: list[dict[str, object]],
) -> str:
    canonical_records = json.dumps(
        validation_records,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(
        canonical_records.encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def _write_json_atomic(
    output_path: Path,
    payload: dict[str, object],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
        ) as temporary_file:
            json.dump(
                payload,
                temporary_file,
                indent=2,
                sort_keys=True,
            )
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _load_score_artifact(
    score_artifact_path: Path,
) -> dict[str, object]:
    try:
        payload = json.loads(
            score_artifact_path.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ThresholdArtifactError(
            "Score artifact could not be loaded."
        ) from exc

    if not isinstance(payload, dict):
        raise ThresholdArtifactError(
            "Score artifact must be a JSON object."
        )

    if payload.get("schema_version") != (
        SCORE_ARTIFACT_SCHEMA_VERSION
    ):
        raise ThresholdArtifactError(
            "Unsupported score-artifact schema version."
        )

    required_lineage = (
        "code_version",
        "dataset",
        "feature_bank",
        "feature_extractor",
        "scorer",
        "records",
    )
    if any(
        key not in payload
        for key in required_lineage
    ):
        raise ThresholdArtifactError(
            "Score artifact lineage is incomplete."
        )

    if not isinstance(payload["records"], list):
        raise ThresholdArtifactError(
            "Score artifact records must be a JSON array."
        )

    feature_bank = payload["feature_bank"]
    if (
        not isinstance(feature_bank, dict)
        or feature_bank.get("split") != "train"
    ):
        raise ThresholdArtifactError(
            "Threshold selection requires a training-only feature bank."
        )

    return payload


def select_threshold_artifact(
    *,
    score_artifact_path: Path,
    artifact_dir: Path,
    quantile: float = DEFAULT_QUANTILE,
    created_at: datetime | None = None,
) -> ThresholdArtifact:
    """Select and atomically store a validation-only threshold."""
    score_payload = _load_score_artifact(
        score_artifact_path
    )
    validation_records = [
        record
        for record in score_payload["records"]
        if (
            isinstance(record, dict)
            and record.get("split") == "validation"
        )
    ]

    if not validation_records:
        raise ThresholdArtifactError(
            "Score artifact contains no validation records."
        )

    if len(
        {
            record.get("sample_id")
            for record in validation_records
        }
    ) != len(validation_records):
        raise ThresholdArtifactError(
            "Validation score sample IDs must be unique."
        )

    try:
        selection = (
            NormalValidationQuantileThresholdSelector()
            .select(
                validation_scores=[
                    record["anomaly_score"]
                    for record in validation_records
                ],
                validation_labels=[
                    record["label"]
                    for record in validation_records
                ],
                split_metadata=[
                    record["split"]
                    for record in validation_records
                ],
                quantile=quantile,
            )
        )
    except (
        KeyError,
        ThresholdSelectionError,
    ) as exc:
        raise ThresholdArtifactError(
            "Validation records cannot satisfy the threshold policy."
        ) from exc

    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ThresholdArtifactError(
            "Creation timestamp must include timezone information."
        )
    created_at_utc = (
        timestamp.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    artifact_dir = artifact_dir.resolve()
    threshold_path = artifact_dir / THRESHOLD_FILENAME
    payload: dict[str, object] = {
        "schema_version": THRESHOLD_ARTIFACT_SCHEMA_VERSION,
        "code_version": THRESHOLD_ARTIFACT_CODE_VERSION,
        "created_at": created_at_utc,
        "calibration": {
            "split": "validation",
            "mode": "normal_only",
            "uses_test_scores": False,
            "uses_test_labels": False,
            "quantile_method": QUANTILE_METHOD,
        },
        "prediction_semantics": {
            "anomalous": "score > threshold",
            "normal": "score <= threshold",
        },
        "threshold_selection": asdict(selection),
        "dataset": score_payload["dataset"],
        "feature_bank": score_payload["feature_bank"],
        "feature_extractor": score_payload[
            "feature_extractor"
        ],
        "scorer": score_payload["scorer"],
        "source_scores": {
            "schema_version": score_payload[
                "schema_version"
            ],
            "code_version": score_payload[
                "code_version"
            ],
            "random_seed": score_payload.get(
                "random_seed"
            ),
            "validation_records_sha256": (
                _validation_records_fingerprint(
                    validation_records
                )
            ),
        },
    }
    _write_json_atomic(threshold_path, payload)

    return ThresholdArtifact(
        artifact_dir=artifact_dir,
        threshold_path=threshold_path,
        selection=selection,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Select a normal-only validation quantile threshold."
        )
    )
    parser.add_argument(
        "--scores",
        type=Path,
        default=(
            DEFAULT_SCORE_ARTIFACT_DIR
            / SCORES_FILENAME
        ),
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=DEFAULT_THRESHOLD_ARTIFACT_DIR,
    )
    parser.add_argument(
        "--quantile",
        type=float,
        default=DEFAULT_QUANTILE,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifact = select_threshold_artifact(
        score_artifact_path=args.scores,
        artifact_dir=args.artifact_dir,
        quantile=args.quantile,
    )

    print("Validation-only threshold selected")
    print(f"Policy: {artifact.selection.threshold_policy}")
    print(f"Quantile: {artifact.selection.quantile}")
    print(f"Threshold: {artifact.selection.threshold}")
    print(
        "Estimated validation false-positive rate: "
        f"{artifact.selection.estimated_validation_false_positive_rate}"
    )
    print(f"Artifact: {artifact.threshold_path}")


if __name__ == "__main__":
    main()
