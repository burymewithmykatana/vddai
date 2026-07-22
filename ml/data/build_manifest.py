from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from ml.data.mvtec_contract import DATASET_ROOT
from ml.data.validate_mvtec import (
    DatasetValidationError,
    ImageRecord,
    MaskAssociation,
    validate_dataset,
)


DEFAULT_VALIDATION_RATIO = 0.2
DEFAULT_RANDOM_SEED = 42


@dataclass(frozen=True)
class ManifestRecord:
    sample_id: str
    image_path: str
    split: str
    label: int
    class_name: str
    is_anomaly: bool
    mask_path: str | None
    width: int
    height: int
    image_format: str
    mode: str


@dataclass(frozen=True)
class DatasetManifest:
    dataset_name: str
    category: str
    dataset_version: str
    random_seed: int
    validation_ratio: float
    records: list[ManifestRecord]


def stable_sample_id(relative_path: str) -> str:
    return hashlib.sha256(
        relative_path.encode("utf-8")
    ).hexdigest()[:16]


def split_training_records(
    training_records: list[ImageRecord],
    validation_ratio: float,
    random_seed: int,
) -> tuple[list[ImageRecord], list[ImageRecord]]:
    if not 0 < validation_ratio < 1:
        raise ValueError(
            "validation_ratio must be between 0 and 1"
        )

    ordered_records = sorted(
        training_records,
        key=lambda record: record.path,
    )

    shuffled_records = ordered_records.copy()
    random.Random(random_seed).shuffle(shuffled_records)

    validation_count = round(
        len(shuffled_records) * validation_ratio
    )

    if validation_count <= 0:
        raise ValueError(
            "validation split would contain no samples"
        )

    if validation_count >= len(shuffled_records):
        raise ValueError(
            "training split would contain no samples"
        )

    validation_paths = {
        record.path
        for record in shuffled_records[:validation_count]
    }

    train_records = [
        record
        for record in ordered_records
        if record.path not in validation_paths
    ]

    validation_records = [
        record
        for record in ordered_records
        if record.path in validation_paths
    ]

    return train_records, validation_records


def build_mask_lookup(
    associations: Iterable[MaskAssociation],
) -> dict[str, str]:
    return {
        association.image_path: association.mask_path
        for association in associations
    }


def to_manifest_record(
    record: ImageRecord,
    split: str,
    mask_lookup: dict[str, str],
) -> ManifestRecord:
    is_anomaly = record.class_name != "good"

    return ManifestRecord(
        sample_id=stable_sample_id(record.path),
        image_path=record.path,
        split=split,
        label=int(is_anomaly),
        class_name=record.class_name,
        is_anomaly=is_anomaly,
        mask_path=mask_lookup.get(record.path),
        width=record.width,
        height=record.height,
        image_format=record.image_format,
        mode=record.mode,
    )


def calculate_dataset_version(
    records: Iterable[ManifestRecord],
) -> str:
    canonical_records = [
        asdict(record)
        for record in sorted(
            records,
            key=lambda item: (
                item.split,
                item.image_path,
            ),
        )
    ]

    canonical_json = json.dumps(
        canonical_records,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()


def build_manifest(
    dataset_root: Path,
    validation_ratio: float = DEFAULT_VALIDATION_RATIO,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> DatasetManifest:
    report, image_records, associations = validate_dataset(
        dataset_root
    )

    if report.corrupt_files:
        raise DatasetValidationError(
            "Cannot build manifest with corrupt files"
        )

    if report.unsupported_files:
        raise DatasetValidationError(
            "Cannot build manifest with unsupported files"
        )

    if report.mask_association_errors:
        raise DatasetValidationError(
            "Cannot build manifest with mask association errors"
        )

    input_records = [
        record
        for record in image_records
        if record.record_type == "image"
    ]

    training_records = [
        record
        for record in input_records
        if record.split == "train"
        and record.class_name == "good"
    ]

    official_test_records = [
        record
        for record in input_records
        if record.split == "test"
    ]

    train_records, validation_records = (
        split_training_records(
            training_records=training_records,
            validation_ratio=validation_ratio,
            random_seed=random_seed,
        )
    )

    mask_lookup = build_mask_lookup(associations)

    manifest_records = [
        *[
            to_manifest_record(
                record=record,
                split="train",
                mask_lookup=mask_lookup,
            )
            for record in train_records
        ],
        *[
            to_manifest_record(
                record=record,
                split="validation",
                mask_lookup=mask_lookup,
            )
            for record in validation_records
        ],
        *[
            to_manifest_record(
                record=record,
                split="test",
                mask_lookup=mask_lookup,
            )
            for record in official_test_records
        ],
    ]

    manifest_records = sorted(
        manifest_records,
        key=lambda record: (
            record.split,
            record.image_path,
        ),
    )

    dataset_version = calculate_dataset_version(
        manifest_records
    )

    return DatasetManifest(
        dataset_name="MVTec AD",
        category="tile",
        dataset_version=dataset_version,
        random_seed=random_seed,
        validation_ratio=validation_ratio,
        records=manifest_records,
    )


def write_json_manifest(
    manifest: DatasetManifest,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            asdict(manifest),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def write_csv_manifest(
    manifest: DatasetManifest,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = list(
        ManifestRecord.__dataclass_fields__.keys()
    )

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for record in manifest.records:
            writer.writerow(asdict(record))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic MVTec AD dataset manifests."
        )
    )

    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DATASET_ROOT,
    )

    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(
            "data/metadata/"
            "mvtec_ad_tile_manifest.generated.json"
        ),
    )

    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path(
            "data/metadata/"
            "mvtec_ad_tile_manifest.generated.csv"
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


def main() -> None:
    args = parse_args()

    manifest = build_manifest(
        dataset_root=args.dataset_root,
        validation_ratio=args.validation_ratio,
        random_seed=args.random_seed,
    )

    write_json_manifest(
        manifest=manifest,
        output_path=args.output_json,
    )

    write_csv_manifest(
        manifest=manifest,
        output_path=args.output_csv,
    )

    split_counts: dict[str, int] = {}

    for record in manifest.records:
        split_counts[record.split] = (
            split_counts.get(record.split, 0) + 1
        )

    print("Dataset manifest generated")
    print(f"Version: {manifest.dataset_version}")
    print(f"Records: {len(manifest.records)}")
    print(f"Split counts: {split_counts}")
    print(f"JSON: {args.output_json}")
    print(f"CSV: {args.output_csv}")


if __name__ == "__main__":
    main()