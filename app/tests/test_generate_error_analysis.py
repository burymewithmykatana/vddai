import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
)
from ml.data.build_manifest import (
    DatasetManifest,
    ManifestRecord,
)
from ml.generate_error_analysis import (
    ERROR_ANALYSIS_CODE_VERSION,
    ERROR_ANALYSIS_SCHEMA_VERSION,
    generate_error_analysis_report,
)

FIXED_CREATED_AT = datetime(
    2026,
    7,
    29,
    18,
    0,
    tzinfo=timezone.utc,
)


def create_image(
    path: Path,
    color: tuple[int, int, int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(
        mode="RGB",
        size=(4, 4),
        color=color,
    ).save(path, format="PNG")


def create_mask(
    path: Path,
    pixels: list[tuple[int, int]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mask = Image.new(
        mode="L",
        size=(4, 4),
        color=0,
    )
    for pixel in pixels:
        mask.putpixel(pixel, 255)
    mask.save(path, format="PNG")


def manifest_record(
    *,
    sample_id: str,
    image_path: str,
    label: int,
    defect_type: str,
    mask_path: str | None,
) -> ManifestRecord:
    return ManifestRecord(
        sample_id=sample_id,
        image_path=image_path,
        split="test",
        label=label,
        class_name=defect_type,
        is_anomaly=label == 1,
        mask_path=mask_path,
        width=4,
        height=4,
        image_format="PNG",
        mode="RGB",
    )


def create_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    dataset_root = tmp_path / "tile"
    records = [
        manifest_record(
            sample_id="tn-001",
            image_path="test/good/001.png",
            label=0,
            defect_type="good",
            mask_path=None,
        ),
        manifest_record(
            sample_id="fp-001",
            image_path="test/good/002.png",
            label=0,
            defect_type="good",
            mask_path=None,
        ),
        manifest_record(
            sample_id="tp-001",
            image_path="test/crack/001.png",
            label=1,
            defect_type="crack",
            mask_path="ground_truth/crack/001_mask.png",
        ),
        manifest_record(
            sample_id="fn-001",
            image_path="test/crack/002.png",
            label=1,
            defect_type="crack",
            mask_path="ground_truth/crack/002_mask.png",
        ),
    ]
    colors = [
        (10, 10, 10),
        (20, 20, 20),
        (200, 200, 200),
        (100, 100, 100),
    ]
    for record, color in zip(records, colors, strict=True):
        create_image(
            dataset_root / record.image_path,
            color,
        )

    create_mask(
        dataset_root / records[2].mask_path,
        [
            (0, 0),
            (1, 0),
            (2, 0),
            (3, 0),
            (0, 1),
            (1, 1),
            (2, 1),
            (3, 1),
        ],
    )
    create_mask(
        dataset_root / records[3].mask_path,
        [(0, 0)],
    )

    manifest = DatasetManifest(
        dataset_name="fake",
        category="tile",
        dataset_version="fake-error-analysis-v1",
        random_seed=42,
        validation_ratio=0.2,
        records=records,
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(asdict(manifest)),
        encoding="utf-8",
    )

    threshold = {
        "threshold_selection": {
            "threshold": 0.5,
        },
    }
    (run_dir / "threshold.json").write_text(
        json.dumps(threshold),
        encoding="utf-8",
    )
    metrics = {
        "dataset": {
            "name": "fake",
            "category": "tile",
            "version": manifest.dataset_version,
            "manifest_fingerprint": "sha256:fake",
        },
        "feature_bank": {
            "split": "train",
        },
        "feature_extractor": {
            "name": "test.fake",
            "pretrained_weights": "none",
        },
        "scorer": {
            "distance": "euclidean",
            "k": 1,
        },
    }
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics),
        encoding="utf-8",
    )

    rows = [
        {
            "sample_id": "tn-001",
            "split": "test",
            "label": 0,
            "defect_type": "good",
            "anomaly_score": 0.1,
            "has_mask": False,
            "source_path": "test/good/001.png",
            "predicted_label": 0,
            "predicted_class": "normal",
        },
        {
            "sample_id": "fp-001",
            "split": "test",
            "label": 0,
            "defect_type": "good",
            "anomaly_score": 0.6,
            "has_mask": False,
            "source_path": "test/good/002.png",
            "predicted_label": 1,
            "predicted_class": "anomalous",
        },
        {
            "sample_id": "tp-001",
            "split": "test",
            "label": 1,
            "defect_type": "crack",
            "anomaly_score": 0.8,
            "has_mask": True,
            "source_path": "test/crack/001.png",
            "predicted_label": 1,
            "predicted_class": "anomalous",
        },
        {
            "sample_id": "fn-001",
            "split": "test",
            "label": 1,
            "defect_type": "crack",
            "anomaly_score": 0.2,
            "has_mask": True,
            "source_path": "test/crack/002.png",
            "predicted_label": 0,
            "predicted_class": "normal",
        },
    ]
    with (run_dir / "sample_scores.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as score_file:
        writer = csv.DictWriter(
            score_file,
            fieldnames=list(rows[0]),
        )
        writer.writeheader()
        writer.writerows(rows)

    return run_dir, manifest_path, dataset_root


def test_machine_and_markdown_reports_are_generated(
    tmp_path: Path,
) -> None:
    (
        run_dir,
        manifest_path,
        dataset_root,
    ) = create_fixture(tmp_path)
    source_image = dataset_root / "test/good/001.png"
    source_before = source_image.read_bytes()

    artifact = generate_error_analysis_report(
        run_dir=run_dir,
        manifest_path=manifest_path,
        dataset_root=dataset_root,
        ranking_limit=2,
        preprocessing_service=ImagePreprocessingService(
            target_width=4,
            target_height=4,
        ),
        created_at=FIXED_CREATED_AT,
    )

    report = json.loads(artifact.machine_report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == (ERROR_ANALYSIS_SCHEMA_VERSION)
    assert report["code_version"] == (ERROR_ANALYSIS_CODE_VERSION)
    assert report["created_at"] == ("2026-07-29T18:00:00Z")
    assert report["outcome_counts"] == {
        "true_positive": 1,
        "true_negative": 1,
        "false_positive": 1,
        "false_negative": 1,
    }
    assert report["rankings"]["highest_scoring_normal"][0]["sample_id"] == "fp-001"
    assert report["rankings"]["lowest_scoring_anomalous"][0]["sample_id"] == "fn-001"
    assert (
        report["rankings"]["most_confident_false_positives"][0]["sample_id"] == "fp-001"
    )
    assert (
        report["rankings"]["most_confident_false_negatives"][0]["sample_id"] == "fn-001"
    )

    anomalous_samples = {
        sample["sample_id"]: sample
        for sample in report["samples"]
        if sample["label"] == 1
    }
    assert anomalous_samples["tp-001"]["mask_properties"]["anomalous_area_ratio"] == 0.5
    assert (
        anomalous_samples["fn-001"]["mask_properties"]["anomalous_area_ratio"] == 0.0625
    )
    assert report["small_anomaly_analysis"]["small_false_negative_rate"] == 1.0
    assert report["small_anomaly_analysis"]["larger_false_negative_rate"] == 0.0
    assert report["limitations"]["pixel_level_localization"] is False
    assert report["configuration"]["visualizations_generated"] is False

    markdown = artifact.markdown_report_path.read_text(encoding="utf-8")
    assert "Ground-Truth Mask Area Analysis" in markdown
    assert "not model-generated heatmaps" in markdown
    assert "Small group: sample count 1, false-negative count 1" in markdown
    assert "False-negative area ratios: count=1" in markdown
    assert "shared deterministic preprocessing contract" in markdown
    assert "fn-001" in markdown
    assert "test/crack/002.png" in markdown
    assert source_image.read_bytes() == source_before
    assert not list(artifact.output_dir.glob(".*"))
