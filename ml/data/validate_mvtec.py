from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ml.data.mvtec_contract import (
    DATASET_ROOT,
    EXPECTED_DIRECTORIES,
)


SUPPORTED_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
}

ALLOWED_NON_IMAGE_FILES = {
    "license.txt",
    "readme.txt",
}


class DatasetValidationError(RuntimeError):
    """Raised when the dataset structure is invalid."""


@dataclass(frozen=True)
class ImageRecord:
    path: str
    split: str
    class_name: str
    record_type: str
    width: int
    height: int
    mode: str
    image_format: str


@dataclass(frozen=True)
class MaskAssociation:
    image_path: str
    mask_path: str
    defect_type: str


@dataclass
class ValidationReport:
    dataset_root: str
    total_images: int
    corrupt_files: list[str]
    unsupported_files: list[str]
    mask_association_errors: list[str]
    input_image_count: int
    mask_count: int
    split_counts: dict[str, int]
    class_counts: dict[str, int]
    dimensions: dict[str, int]
    formats: dict[str, int]
    modes: dict[str, int]


def validate_required_directories(dataset_root: Path) -> None:
    missing = [
        directory
        for directory in EXPECTED_DIRECTORIES
        if not (dataset_root / directory).is_dir()
    ]

    if missing:
        raise DatasetValidationError(
            "Missing required dataset directories: "
            + ", ".join(missing)
        )


def infer_split_and_class(
    image_path: Path,
    dataset_root: Path,
) -> tuple[str, str]:
    relative_path = image_path.relative_to(dataset_root)
    parts = relative_path.parts

    if len(parts) < 3:
        raise DatasetValidationError(
            f"Unexpected image path structure: {relative_path}"
        )

    split = parts[0]
    class_name = parts[1]

    return split, class_name


def inspect_image(
    image_path: Path,
    dataset_root: Path,
) -> ImageRecord:
    split, class_name = infer_split_and_class(
        image_path=image_path,
        dataset_root=dataset_root,
    )

    with Image.open(image_path) as image:
        image.verify()

    with Image.open(image_path) as image:
        width, height = image.size
        mode = image.mode
        image_format = image.format or "unknown"

    record_type = (
        "mask" if split == "ground_truth"
        else "image"
    )

    return ImageRecord(
        path=image_path.relative_to(dataset_root).as_posix(),
        split=split,
        class_name=class_name,
        record_type=record_type,
        width=width,
        height=height,
        mode=mode,
        image_format=image_format,
    )


def collect_image_paths(
    dataset_root: Path,
) -> tuple[list[Path], list[str]]:
    image_paths: list[Path] = []
    unsupported_files: list[str] = []

    for file_path in sorted(dataset_root.rglob("*")):
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() in SUPPORTED_SUFFIXES:
            image_paths.append(file_path)
            continue

        if file_path.name.lower() in ALLOWED_NON_IMAGE_FILES:
            continue

        unsupported_files.append(
            file_path.relative_to(dataset_root).as_posix()
        )

    return image_paths, unsupported_files


def expected_mask_path(
    image_record: ImageRecord,
    dataset_root: Path,
) -> Path:
    image_name = Path(image_record.path).stem

    return (
        dataset_root
        / "ground_truth"
        / image_record.class_name
        / f"{image_name}_mask.png"
    )


def validate_mask_associations(
    records: list[ImageRecord],
    dataset_root: Path,
) -> tuple[list[MaskAssociation], list[str]]:
    associations: list[MaskAssociation] = []
    errors: list[str] = []

    mask_records = {
        record.path
        for record in records
        if record.record_type == "mask"
    }

    defective_test_records = [
        record
        for record in records
        if record.split == "test"
        and record.class_name != "good"
        and record.record_type == "image"
    ]

    expected_mask_records: set[str] = set()

    for record in defective_test_records:
        mask_path = expected_mask_path(
            image_record=record,
            dataset_root=dataset_root,
        )

        relative_mask_path = mask_path.relative_to(
            dataset_root
        ).as_posix()

        expected_mask_records.add(relative_mask_path)

        if relative_mask_path not in mask_records:
            errors.append(
                "Missing mask for defective test image: "
                f"{record.path} -> {relative_mask_path}"
            )
            continue

        associations.append(
            MaskAssociation(
                image_path=record.path,
                mask_path=relative_mask_path,
                defect_type=record.class_name,
            )
        )

    orphan_masks = sorted(
        mask_records - expected_mask_records
    )

    for mask_path in orphan_masks:
        errors.append(
            f"Orphan ground-truth mask: {mask_path}"
        )

    return associations, errors


def validate_dataset(
    dataset_root: Path,
) -> tuple[ValidationReport, list[ImageRecord]]:
    dataset_root = dataset_root.resolve()

    if not dataset_root.is_dir():
        raise DatasetValidationError(
            f"Dataset root does not exist: {dataset_root}"
        )

    validate_required_directories(dataset_root)

    image_paths, unsupported_files = collect_image_paths(
        dataset_root
    )

    if not image_paths:
        raise DatasetValidationError(
            f"No supported images found under: {dataset_root}"
        )

    records: list[ImageRecord] = []
    corrupt_files: list[str] = []

    for image_path in image_paths:
        try:
            records.append(
                inspect_image(
                    image_path=image_path,
                    dataset_root=dataset_root,
                )
            )
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            DatasetValidationError,
        ) as exc:
            relative_path = image_path.relative_to(
                dataset_root
            ).as_posix()

            corrupt_files.append(
                f"{relative_path}: {exc}"
            )

    split_counts = Counter(
        record.split for record in records
    )

    class_counts = Counter(
        f"{record.split}/{record.class_name}"
        for record in records
    )

    dimensions = Counter(
        f"{record.width}x{record.height}"
        for record in records
    )

    formats = Counter(
        record.image_format for record in records
    )

    modes = Counter(
        record.mode for record in records
    )

    associations, mask_association_errors = (
        validate_mask_associations(
            records=records,
            dataset_root=dataset_root,
        )
    )
    
    input_image_count = sum(
        record.record_type == "image"
        for record in records
    )

    mask_count = sum(
        record.record_type == "mask"
        for record in records
    )
    
    report = ValidationReport(
        dataset_root=str(dataset_root),
        total_images=len(records),
        corrupt_files=corrupt_files,
        unsupported_files=unsupported_files,
        split_counts=dict(sorted(split_counts.items())),
        class_counts=dict(sorted(class_counts.items())),
        dimensions=dict(sorted(dimensions.items())),
        formats=dict(sorted(formats.items())),
        modes=dict(sorted(modes.items())),
        mask_association_errors=mask_association_errors,
        input_image_count=input_image_count,
        mask_count=mask_count,
    )

    return report, records, associations


def write_json(
    output_path: Path,
    data: object,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )
        file.write("\n")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate MVTec AD tile structure and image integrity."
        )
    )

    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DATASET_ROOT,
    )

    parser.add_argument(
        "--report",
        type=Path,
        default=Path(
            "data/metadata/"
            "mvtec_ad_tile_validation.generated.json"
        ),
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "data/metadata/"
            "mvtec_ad_tile_manifest.generated.json"
        ),
    )

    parser.add_argument(
        "--associations",
        type=Path,
        default=Path(
            "data/metadata/"
            "mvtec_ad_tile_associations.generated.json"
        ),
    )
    
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()

    try:
        report, records, associations = validate_dataset(
            dataset_root=arguments.dataset_root,
        )
    except DatasetValidationError as exc:
        raise SystemExit(
            f"Dataset validation failed: {exc}"
        ) from exc

    write_json(
        output_path=arguments.report,
        data=asdict(report),
    )

    write_json(
        output_path=arguments.manifest,
        data=[asdict(record) for record in records],
    )

    write_json(
        output_path=arguments.associations,
        data=[
            asdict(association)
            for association in associations
        ],
    )
    
    print(f"Dataset root: {report.dataset_root}")
    print(f"Valid images: {report.total_images}")
    print(f"Corrupt files: {len(report.corrupt_files)}")
    print(
        f"Unsupported files: "
        f"{len(report.unsupported_files)}"
    )
    print(f"Split counts: {report.split_counts}")
    print(f"Class counts: {report.class_counts}")
    print(f"Dimensions: {report.dimensions}")
    print(f"Formats: {report.formats}")
    print(f"Modes: {report.modes}")
    print(f"Report written to: {arguments.report}")
    print(f"Manifest written to: {arguments.manifest}")
    print(f"Input images: {report.input_image_count}")
    print(f"Masks: {report.mask_count}")
    print(
        "Mask association errors: "
        f"{len(report.mask_association_errors)}"
    )
    print(
        f"Associations written to: "
        f"{arguments.associations}"
    )
    
    if (
    report.corrupt_files
    or report.unsupported_files
    or report.mask_association_errors
    ):
        raise SystemExit(
            "Dataset validation failed because integrity "
            "violations were found."
        )


if __name__ == "__main__":
    main()