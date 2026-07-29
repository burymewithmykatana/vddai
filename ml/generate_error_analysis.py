"""Generate segmentation-aware qualitative error-analysis reports.

The model remains image-level. Ground-truth segmentation masks are used only
to describe annotated defects after prediction; they are not model heatmaps
and do not imply pixel-level localization capability.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
    image_preprocessing_service,
)
from ml.data.build_manifest import (
    DatasetManifest,
    ManifestRecord,
    read_json_manifest,
)
from ml.data.dataset import preprocess_mask
from ml.data.mvtec_contract import DATASET_ROOT
from ml.data.process_manifest import resolve_manifest_path
from ml.error_analysis import (
    AreaRatioSummary,
    ErrorAnalysisError,
    ErrorAnalysisSample,
    Rankings,
    SmallAnomalyAnalysis,
    analyze_small_anomalies,
    categorize_outcome,
    count_outcomes,
    describe_mask,
    rank_error_samples,
)
from ml.generate_feature_bank import DEFAULT_MANIFEST_PATH

ERROR_ANALYSIS_SCHEMA_VERSION = "vddai.error_analysis.v1"
ERROR_ANALYSIS_CODE_VERSION = "vddai.error_analysis.generator.v1"
MACHINE_REPORT_FILENAME = "error_analysis.json"
MARKDOWN_REPORT_FILENAME = "error_analysis.md"
DEFAULT_RANKING_LIMIT = 10

ExistingReportPolicy = Literal["error", "overwrite"]


class ErrorAnalysisReportError(RuntimeError):
    """Raised when a safe error-analysis report cannot be generated."""


@dataclass(frozen=True)
class ErrorAnalysisArtifacts:
    output_dir: Path
    machine_report_path: Path
    markdown_report_path: Path
    samples: tuple[ErrorAnalysisSample, ...]
    rankings: Rankings
    small_anomaly_analysis: SmallAnomalyAnalysis


def _write_text(
    output_path: Path,
    content: str,
) -> None:
    with output_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as output_file:
        output_file.write(content)
        output_file.flush()
        os.fsync(output_file.fileno())


def _load_json_object(
    path: Path,
    *,
    name: str,
) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorAnalysisReportError(f"{name} could not be loaded.") from exc

    if not isinstance(payload, dict):
        raise ErrorAnalysisReportError(f"{name} must be a JSON object.")

    return payload


def _load_score_rows(
    path: Path,
) -> list[dict[str, str]]:
    try:
        with path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as score_file:
            rows = list(csv.DictReader(score_file))
    except OSError as exc:
        raise ErrorAnalysisReportError(
            "Per-sample score CSV could not be loaded."
        ) from exc

    required_fields = {
        "sample_id",
        "split",
        "label",
        "defect_type",
        "anomaly_score",
        "has_mask",
        "source_path",
        "predicted_label",
        "predicted_class",
    }
    if not rows or not required_fields.issubset(rows[0].keys()):
        raise ErrorAnalysisReportError(
            "Per-sample score CSV does not match the expected schema."
        )

    return rows


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ErrorAnalysisReportError("Boolean CSV fields must use true or false.")


def _test_manifest_records(
    manifest: DatasetManifest,
) -> dict[str, ManifestRecord]:
    records = {
        record.sample_id: record
        for record in manifest.records
        if record.split == "test"
    }

    if not records:
        raise ErrorAnalysisReportError("Manifest contains no test records.")

    return records


def _build_samples(
    *,
    score_rows: list[dict[str, str]],
    manifest: DatasetManifest,
    dataset_root: Path,
    threshold: float,
    preprocessing_service: ImagePreprocessingService,
) -> tuple[ErrorAnalysisSample, ...]:
    manifest_records = _test_manifest_records(manifest)
    sample_ids = [row["sample_id"] for row in score_rows]

    if len(set(sample_ids)) != len(sample_ids):
        raise ErrorAnalysisReportError("Per-sample score IDs must be unique.")

    if set(sample_ids) != set(manifest_records):
        raise ErrorAnalysisReportError(
            "Per-sample scores must match the manifest test split."
        )

    samples: list[ErrorAnalysisSample] = []

    for row in score_rows:
        if row["split"] != "test":
            raise ErrorAnalysisReportError("Error analysis accepts test records only.")

        manifest_record = manifest_records[row["sample_id"]]

        try:
            label = int(row["label"])
            predicted_label = int(row["predicted_label"])
            anomaly_score = float(row["anomaly_score"])
        except ValueError as exc:
            raise ErrorAnalysisReportError(
                "Score CSV contains invalid numeric values."
            ) from exc

        if not np.isfinite(anomaly_score):
            raise ErrorAnalysisReportError("Anomaly scores must be finite.")

        expected_predicted_class = "anomalous" if predicted_label == 1 else "normal"
        if row["predicted_class"] != expected_predicted_class:
            raise ErrorAnalysisReportError(
                "Stored predicted class does not match its label."
            )

        expected_prediction = int(anomaly_score > threshold)
        if predicted_label != expected_prediction:
            raise ErrorAnalysisReportError(
                "Stored prediction does not match the frozen threshold."
            )

        if (
            label != manifest_record.label
            or row["defect_type"] != manifest_record.class_name
            or row["source_path"] != manifest_record.image_path
        ):
            raise ErrorAnalysisReportError(
                "Score metadata does not match the test manifest."
            )

        resolve_manifest_path(
            dataset_root=dataset_root,
            relative_path=manifest_record.image_path,
        )

        has_mask = _parse_bool(row["has_mask"])
        manifest_has_mask = manifest_record.mask_path is not None
        if has_mask != manifest_has_mask:
            raise ErrorAnalysisReportError(
                "Mask metadata does not match the test manifest."
            )

        mask_properties = None
        if label == 1:
            if manifest_record.mask_path is None:
                mask_properties = describe_mask(None)
            else:
                mask_file = resolve_manifest_path(
                    dataset_root=dataset_root,
                    relative_path=(manifest_record.mask_path),
                )
                mask = preprocess_mask(
                    mask_path=mask_file,
                    target_width=(preprocessing_service.target_width),
                    target_height=(preprocessing_service.target_height),
                )
                mask_properties = describe_mask(mask)

        outcome = categorize_outcome(
            label=label,
            predicted_label=predicted_label,
        )
        samples.append(
            ErrorAnalysisSample(
                sample_id=manifest_record.sample_id,
                source_path=(manifest_record.image_path),
                mask_path=manifest_record.mask_path,
                label=label,
                predicted_label=predicted_label,
                actual_class=("anomalous" if label == 1 else "normal"),
                predicted_class=("anomalous" if predicted_label == 1 else "normal"),
                defect_type=manifest_record.class_name,
                anomaly_score=anomaly_score,
                threshold=threshold,
                has_mask=has_mask,
                outcome=outcome,
                mask_properties=mask_properties,
            )
        )

    return tuple(samples)


def _markdown_escape(value: object) -> str:
    return str(value).replace("|", "\\|")


def _ranking_markdown(
    title: str,
    samples: tuple[ErrorAnalysisSample, ...],
) -> list[str]:
    lines = [
        f"### {title}",
        "",
    ]
    if not samples:
        lines.extend(
            [
                "No samples in this category.",
                "",
            ]
        )
        return lines

    lines.extend(
        [
            "| Rank | Sample ID | Score | Outcome | Defect | Relative path |",
            "|---:|---|---:|---|---|---|",
        ]
    )
    for index, sample in enumerate(samples, start=1):
        lines.append(
            "| "
            f"{index} | "
            f"{_markdown_escape(sample.sample_id)} | "
            f"{sample.anomaly_score:.6f} | "
            f"{sample.outcome} | "
            f"{_markdown_escape(sample.defect_type)} | "
            f"{_markdown_escape(sample.source_path)} |"
        )
    lines.append("")
    return lines


def _optional_float(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.6f}"


def _area_summary_text(
    summary: AreaRatioSummary | None,
) -> str:
    if summary is None:
        return "unavailable"
    return (
        f"count={summary.count}, "
        f"mean={summary.mean:.6f}, "
        f"median={summary.median:.6f}, "
        f"min={summary.minimum:.6f}, "
        f"max={summary.maximum:.6f}"
    )


def _build_markdown(
    *,
    report: dict[str, object],
    rankings: Rankings,
    small_anomaly_analysis: SmallAnomalyAnalysis,
    samples: tuple[ErrorAnalysisSample, ...],
) -> str:
    counts = report["outcome_counts"]
    lines = [
        "# VDDAI Image-Level Error Analysis",
        "",
        "> Important limitation: this baseline produces one image-level "
        "anomaly score per image. Ground-truth masks below are dataset "
        "annotations used for descriptive analysis, not model-generated "
        "heatmaps or evidence of pixel-level localization.",
        "",
        "## Outcome Summary",
        "",
        "| Outcome | Count |",
        "|---|---:|",
        f"| True positive | {counts['true_positive']} |",
        f"| True negative | {counts['true_negative']} |",
        f"| False positive | {counts['false_positive']} |",
        f"| False negative | {counts['false_negative']} |",
        "",
        "## Ranked Review Queues",
        "",
    ]
    lines.extend(
        _ranking_markdown(
            "Highest-Scoring Normal Images",
            rankings.highest_scoring_normal,
        )
    )
    lines.extend(
        _ranking_markdown(
            "Lowest-Scoring Anomalous Images",
            rankings.lowest_scoring_anomalous,
        )
    )
    lines.extend(
        _ranking_markdown(
            "Most Confident False Positives",
            rankings.most_confident_false_positives,
        )
    )
    lines.extend(
        _ranking_markdown(
            "Most Confident False Negatives",
            rankings.most_confident_false_negatives,
        )
    )

    lines.extend(
        [
            "## Ground-Truth Mask Area Analysis",
            "",
            small_anomaly_analysis.definition,
            "Pixel counts and area ratios use masks resized by the shared "
            "deterministic preprocessing contract.",
            "",
            f"- Annotated anomalous samples: "
            f"{small_anomaly_analysis.annotated_anomalous_sample_count}",
            f"- Median anomalous area ratio: "
            f"{_optional_float(small_anomaly_analysis.median_area_ratio)}",
            "- Small group: sample count "
            f"{small_anomaly_analysis.small_sample_count}, false-negative "
            f"count {small_anomaly_analysis.small_false_negative_count}, "
            "false-negative rate "
            f"{_optional_float(small_anomaly_analysis.small_false_negative_rate)}",
            "- Larger group: sample count "
            f"{small_anomaly_analysis.larger_sample_count}, false-negative "
            f"count {small_anomaly_analysis.larger_false_negative_count}, "
            "false-negative rate "
            f"{_optional_float(small_anomaly_analysis.larger_false_negative_rate)}",
            "- True-positive area ratios: "
            f"{_area_summary_text(small_anomaly_analysis.true_positive_area_ratios)}",
            "- False-negative area ratios: "
            f"{_area_summary_text(small_anomaly_analysis.false_negative_area_ratios)}",
            f"- Observation: {small_anomaly_analysis.observation}",
            "",
            "### False-Negative Mask Details",
            "",
            "| Sample ID | Score | Defect | Area ratio | Pixels | Bounding box | Relative path |",
            "|---|---:|---|---:|---:|---|---|",
        ]
    )
    false_negatives = [
        sample for sample in samples if sample.outcome == "false_negative"
    ]
    for sample in sorted(
        false_negatives,
        key=lambda item: (
            item.anomaly_score,
            item.sample_id,
        ),
    ):
        properties = sample.mask_properties
        area_ratio = properties.anomalous_area_ratio if properties is not None else None
        pixel_count = (
            properties.anomalous_pixel_count if properties is not None else None
        )
        bounding_box = (
            asdict(properties.bounding_box)
            if (properties is not None and properties.bounding_box is not None)
            else None
        )
        lines.append(
            "| "
            f"{_markdown_escape(sample.sample_id)} | "
            f"{sample.anomaly_score:.6f} | "
            f"{_markdown_escape(sample.defect_type)} | "
            f"{_optional_float(area_ratio)} | "
            f"{pixel_count if pixel_count is not None else 'unavailable'} | "
            f"{_markdown_escape(bounding_box)} | "
            f"{_markdown_escape(sample.source_path)} |"
        )
    if not false_negatives:
        lines.append("| - | - | - | - | - | - | No false negatives |")

    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "- Connected-component counts were not calculated; area and "
            "bounding-box properties are sufficient for this baseline.",
            "- No contact sheets, overlays, model heatmaps, or source-image "
            "modifications were generated.",
            "- These official-test observations are for qualitative error "
            "analysis and must not be used to retune the Week 4 model or "
            "threshold.",
            "",
            "## Lineage",
            "",
            f"- Dataset version: `{report['dataset']['version']}`",
            f"- Feature extractor: " f"`{report['feature_extractor']['name']}`",
            f"- Pretrained weights: "
            f"`{report['feature_extractor']['pretrained_weights']}`",
            f"- Threshold: `{report['threshold']}`",
            f"- Ranking limit: `{report['configuration']['ranking_limit']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _publish_reports(
    *,
    stage_dir: Path,
    output_dir: Path,
    existing_report_policy: ExistingReportPolicy,
) -> None:
    if not output_dir.exists():
        os.replace(stage_dir, output_dir)
        return

    if not output_dir.is_dir():
        raise ErrorAnalysisReportError("Error-analysis output path is not a directory.")

    if existing_report_policy != "overwrite":
        raise ErrorAnalysisReportError("Error-analysis output already exists.")

    for filename in (
        MACHINE_REPORT_FILENAME,
        MARKDOWN_REPORT_FILENAME,
    ):
        os.replace(
            stage_dir / filename,
            output_dir / filename,
        )
    stage_dir.rmdir()


def generate_error_analysis_report(
    *,
    run_dir: Path,
    manifest_path: Path,
    dataset_root: Path,
    output_dir: Path | None = None,
    ranking_limit: int = DEFAULT_RANKING_LIMIT,
    existing_report_policy: ExistingReportPolicy = "error",
    preprocessing_service: ImagePreprocessingService = (image_preprocessing_service),
    created_at: datetime | None = None,
) -> ErrorAnalysisArtifacts:
    """Generate JSON and Markdown reports from one frozen evaluation run."""
    if existing_report_policy not in {
        "error",
        "overwrite",
    }:
        raise ErrorAnalysisReportError(
            "Existing-report policy must be error or overwrite."
        )

    run_dir = run_dir.resolve()
    output_dir = (
        output_dir.resolve() if output_dir is not None else run_dir / "error_analysis"
    )

    try:
        output_dir.relative_to(run_dir)
    except ValueError as exc:
        raise ErrorAnalysisReportError(
            "Error-analysis output must stay inside the run directory."
        ) from exc

    if output_dir.exists() and existing_report_policy == "error":
        raise ErrorAnalysisReportError("Error-analysis output already exists.")

    metrics = _load_json_object(
        run_dir / "metrics.json",
        name="Evaluation metrics",
    )
    threshold_metadata = _load_json_object(
        run_dir / "threshold.json",
        name="Threshold metadata",
    )
    score_rows = _load_score_rows(run_dir / "sample_scores.csv")
    manifest = read_json_manifest(manifest_path)

    try:
        threshold = float(threshold_metadata["threshold_selection"]["threshold"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ErrorAnalysisReportError("Threshold metadata is incomplete.") from exc
    if not np.isfinite(threshold):
        raise ErrorAnalysisReportError("Threshold must be finite.")

    dataset_lineage = metrics.get("dataset")
    if (
        not isinstance(dataset_lineage, dict)
        or dataset_lineage.get("version") != manifest.dataset_version
    ):
        raise ErrorAnalysisReportError(
            "Evaluation and manifest dataset versions must match."
        )

    feature_extractor_lineage = metrics.get("feature_extractor")
    if (
        not isinstance(feature_extractor_lineage, dict)
        or not isinstance(
            feature_extractor_lineage.get("name"),
            str,
        )
        or not isinstance(
            feature_extractor_lineage.get("pretrained_weights"),
            str,
        )
    ):
        raise ErrorAnalysisReportError("Feature-extractor lineage is incomplete.")

    try:
        samples = _build_samples(
            score_rows=score_rows,
            manifest=manifest,
            dataset_root=dataset_root,
            threshold=threshold,
            preprocessing_service=preprocessing_service,
        )
        rankings = rank_error_samples(
            samples,
            limit=ranking_limit,
        )
        small_anomaly_analysis = analyze_small_anomalies(samples)
    except ErrorAnalysisError as exc:
        raise ErrorAnalysisReportError("Error-analysis inputs are invalid.") from exc

    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ErrorAnalysisReportError(
            "Creation timestamp must include timezone information."
        )
    created_at_utc = (
        timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    report: dict[str, object] = {
        "schema_version": ERROR_ANALYSIS_SCHEMA_VERSION,
        "code_version": ERROR_ANALYSIS_CODE_VERSION,
        "created_at": created_at_utc,
        "limitations": {
            "model_output": "image_level_anomaly_score",
            "pixel_level_localization": False,
            "mask_usage": ("ground_truth_annotation_for_descriptive_analysis_only"),
            "model_heatmaps_generated": False,
            "retune_week4_from_test_errors": False,
        },
        "configuration": {
            "ranking_limit": ranking_limit,
            "small_anomaly_policy": ("area_ratio_at_or_below_annotated_anomaly_median"),
            "connected_component_count": "not_calculated",
            "visualizations_generated": False,
        },
        "dataset": dataset_lineage,
        "feature_bank": metrics.get("feature_bank"),
        "feature_extractor": feature_extractor_lineage,
        "scorer": metrics.get("scorer"),
        "threshold": threshold,
        "outcome_counts": count_outcomes(samples),
        "rankings": asdict(rankings),
        "small_anomaly_analysis": asdict(small_anomaly_analysis),
        "samples": [asdict(sample) for sample in samples],
    }
    markdown = _build_markdown(
        report=report,
        rankings=rankings,
        small_anomaly_analysis=small_anomaly_analysis,
        samples=samples,
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(
        tempfile.mkdtemp(
            dir=output_dir.parent,
            prefix=f".{output_dir.name}.",
        )
    )

    try:
        _write_text(
            stage_dir / MACHINE_REPORT_FILENAME,
            json.dumps(
                report,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        _write_text(
            stage_dir / MARKDOWN_REPORT_FILENAME,
            markdown,
        )
        _publish_reports(
            stage_dir=stage_dir,
            output_dir=output_dir,
            existing_report_policy=(existing_report_policy),
        )
    except (OSError, ErrorAnalysisReportError) as exc:
        if stage_dir.exists():
            shutil.rmtree(stage_dir)
        if isinstance(exc, ErrorAnalysisReportError):
            raise
        raise ErrorAnalysisReportError(
            "Error-analysis reports could not be written."
        ) from exc

    return ErrorAnalysisArtifacts(
        output_dir=output_dir,
        machine_report_path=(output_dir / MACHINE_REPORT_FILENAME),
        markdown_report_path=(output_dir / MARKDOWN_REPORT_FILENAME),
        samples=samples,
        rankings=rankings,
        small_anomaly_analysis=small_anomaly_analysis,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Generate segmentation-aware image-level error analysis.")
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DATASET_ROOT,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--ranking-limit",
        type=int,
        default=DEFAULT_RANKING_LIMIT,
    )
    parser.add_argument(
        "--existing-report-policy",
        choices=("error", "overwrite"),
        default="error",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifact = generate_error_analysis_report(
        run_dir=args.run_dir,
        manifest_path=args.manifest,
        dataset_root=args.dataset_root,
        output_dir=args.output_dir,
        ranking_limit=args.ranking_limit,
        existing_report_policy=(args.existing_report_policy),
    )

    counts = count_outcomes(artifact.samples)
    print("Segmentation-aware error analysis generated")
    print(f"Outcome counts: {counts}")
    print(f"Machine report: {artifact.machine_report_path}")
    print(f"Markdown report: {artifact.markdown_report_path}")


if __name__ == "__main__":
    main()
