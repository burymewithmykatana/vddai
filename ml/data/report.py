from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
    image_preprocessing_service,
)
from ml.data.build_manifest import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_VALIDATION_RATIO,
    DatasetManifest,
    build_manifest,
)
from ml.data.dataset import (
    ManifestDataset,
    collate_samples,
)
from ml.data.mvtec_contract import DATASET_ROOT
from ml.data.validate_mvtec import (
    DatasetValidationError,
    validate_dataset,
)


@dataclass(frozen=True)
class BatchContractReport:
    images_shape: tuple[int, ...]
    images_dtype: str
    labels_shape: tuple[int, ...]
    labels_dtype: str
    masks_shape: tuple[int, ...]
    masks_dtype: str
    has_masks_shape: tuple[int, ...]
    has_masks_dtype: str


@dataclass(frozen=True)
class DatasetPipelineReport:
    dataset_name: str
    category: str
    dataset_root: str
    dataset_version: str
    random_seed: int
    validation_ratio: float
    input_image_count: int
    mask_count: int
    manifest_record_count: int
    split_counts: dict[str, int]
    class_counts: dict[str, int]
    anomaly_counts: dict[str, int]
    mask_counts_by_split: dict[str, int]
    corrupt_file_count: int
    unsupported_file_count: int
    mask_association_error_count: int
    preprocessing_width: int
    preprocessing_height: int
    batch_contract: BatchContractReport


def count_manifest_splits(
    manifest: DatasetManifest,
) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                record.split
                for record in manifest.records
            ).items()
        )
    )


def count_manifest_classes(
    manifest: DatasetManifest,
) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                f"{record.split}/{record.class_name}"
                for record in manifest.records
            ).items()
        )
    )


def count_anomalies(
    manifest: DatasetManifest,
) -> dict[str, int]:
    counts: Counter[str] = Counter()

    for record in manifest.records:
        key = (
            f"{record.split}/anomaly"
            if record.is_anomaly
            else f"{record.split}/normal"
        )
        counts[key] += 1

    return dict(sorted(counts.items()))


def count_masks_by_split(
    manifest: DatasetManifest,
) -> dict[str, int]:
    counts: Counter[str] = Counter()

    for record in manifest.records:
        if record.mask_path is not None:
            counts[record.split] += 1

    return dict(sorted(counts.items()))


def select_batch_records(
    manifest: DatasetManifest,
) -> list:
    test_records = [
        record
        for record in manifest.records
        if record.split == "test"
    ]

    normal_record = next(
        (
            record
            for record in test_records
            if not record.is_anomaly
        ),
        None,
    )

    anomaly_record = next(
        (
            record
            for record in test_records
            if record.is_anomaly
        ),
        None,
    )

    if normal_record is None:
        raise DatasetValidationError(
            "The test split contains no normal sample."
        )

    if anomaly_record is None:
        raise DatasetValidationError(
            "The test split contains no anomalous sample."
        )

    return [
        normal_record,
        anomaly_record,
    ]


def build_batch_contract(
    manifest: DatasetManifest,
    dataset_root: Path,
    preprocessing_service: ImagePreprocessingService,
) -> BatchContractReport:
    test_dataset = ManifestDataset(
        manifest=manifest,
        dataset_root=dataset_root,
        split="test",
        preprocessing_service=preprocessing_service,
    )

    selected_records = select_batch_records(manifest)

    records_by_id = {
        record.sample_id: index
        for index, record in enumerate(
            test_dataset.records
        )
    }

    samples = [
        test_dataset[
            records_by_id[record.sample_id]
        ]
        for record in selected_records
    ]

    batch = collate_samples(samples)

    return BatchContractReport(
        images_shape=tuple(batch.images.shape),
        images_dtype=str(batch.images.dtype),
        labels_shape=tuple(batch.labels.shape),
        labels_dtype=str(batch.labels.dtype),
        masks_shape=tuple(batch.masks.shape),
        masks_dtype=str(batch.masks.dtype),
        has_masks_shape=tuple(batch.has_masks.shape),
        has_masks_dtype=str(batch.has_masks.dtype),
    )


def build_pipeline_report(
    dataset_root: Path,
    validation_ratio: float = DEFAULT_VALIDATION_RATIO,
    random_seed: int = DEFAULT_RANDOM_SEED,
    preprocessing_service: ImagePreprocessingService = (
        image_preprocessing_service
    ),
) -> DatasetPipelineReport:
    validation_report, _, _ = validate_dataset(
        dataset_root
    )

    integrity_errors = (
        validation_report.corrupt_files
        or validation_report.unsupported_files
        or validation_report.mask_association_errors
    )

    if integrity_errors:
        raise DatasetValidationError(
            "Cannot build pipeline report because "
            "dataset integrity violations were found."
        )

    manifest = build_manifest(
        dataset_root=dataset_root,
        validation_ratio=validation_ratio,
        random_seed=random_seed,
    )

    batch_contract = build_batch_contract(
        manifest=manifest,
        dataset_root=dataset_root,
        preprocessing_service=preprocessing_service,
    )

    return DatasetPipelineReport(
        dataset_name=manifest.dataset_name,
        category=manifest.category,
        dataset_root=str(dataset_root.resolve()),
        dataset_version=manifest.dataset_version,
        random_seed=manifest.random_seed,
        validation_ratio=manifest.validation_ratio,
        input_image_count=(
            validation_report.input_image_count
        ),
        mask_count=validation_report.mask_count,
        manifest_record_count=len(manifest.records),
        split_counts=count_manifest_splits(manifest),
        class_counts=count_manifest_classes(manifest),
        anomaly_counts=count_anomalies(manifest),
        mask_counts_by_split=count_masks_by_split(
            manifest
        ),
        corrupt_file_count=len(
            validation_report.corrupt_files
        ),
        unsupported_file_count=len(
            validation_report.unsupported_files
        ),
        mask_association_error_count=len(
            validation_report.mask_association_errors
        ),
        preprocessing_width=(
            preprocessing_service.target_width
        ),
        preprocessing_height=(
            preprocessing_service.target_height
        ),
        batch_contract=batch_contract,
    )


def write_pipeline_report(
    report: DatasetPipelineReport,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            asdict(report),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete VDDAI dataset pipeline "
            "and generate its reproducibility report."
        )
    )

    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DATASET_ROOT,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/metadata/"
            "mvtec_ad_tile_pipeline.generated.json"
        ),
    )

    parser.add_argument(
        "--validation-ratio",
        type=float,
        default=DEFAULT_VALIDATION_RATIO,
    )

    parser.add_argument(
        "--random-seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
    )

    return parser.parse_args()


def print_report(
    report: DatasetPipelineReport,
) -> None:
    print("Dataset pipeline verified")
    print(f"Dataset: {report.dataset_name}")
    print(f"Category: {report.category}")
    print(f"Version: {report.dataset_version}")
    print(
        f"Input images: {report.input_image_count}"
    )
    print(f"Masks: {report.mask_count}")
    print(f"Splits: {report.split_counts}")
    print(f"Classes: {report.class_counts}")
    print(f"Anomalies: {report.anomaly_counts}")
    print(
        "Masks by split: "
        f"{report.mask_counts_by_split}"
    )
    print(
        "Preprocessing: "
        f"{report.preprocessing_width}x"
        f"{report.preprocessing_height}"
    )
    print(
        "Image batch: "
        f"{report.batch_contract.images_shape} "
        f"{report.batch_contract.images_dtype}"
    )
    print(
        "Mask batch: "
        f"{report.batch_contract.masks_shape} "
        f"{report.batch_contract.masks_dtype}"
    )


def main() -> None:
    args = parse_args()

    try:
        report = build_pipeline_report(
            dataset_root=args.dataset_root,
            validation_ratio=args.validation_ratio,
            random_seed=args.random_seed,
        )
    except DatasetValidationError as exc:
        raise SystemExit(
            f"Dataset pipeline verification failed: {exc}"
        ) from exc

    write_pipeline_report(
        report=report,
        output_path=args.output,
    )

    print_report(report)
    print(f"Report written to: {args.output}")


if __name__ == "__main__":
    main()