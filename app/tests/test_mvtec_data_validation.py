from pathlib import Path

import pytest
from PIL import Image

from ml.data.validate_mvtec import (
    DatasetValidationError,
    validate_dataset,
)


def create_png(path: Path, mode: str = "RGB") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new(
        mode=mode,
        size=(32, 32),
        color=0,
    )
    image.save(path, format="PNG")


def create_minimal_valid_dataset(root: Path) -> None:
    create_png(root / "train" / "good" / "001.png")
    create_png(root / "test" / "good" / "001.png")
    create_png(root / "test" / "crack" / "001.png")

    create_png(
        root
        / "ground_truth"
        / "crack"
        / "001_mask.png",
        mode="L",
    )


def test_valid_dataset_passes(tmp_path: Path) -> None:
    dataset_root = tmp_path / "tile"
    create_minimal_valid_dataset(dataset_root)

    report, records, associations = validate_dataset(
        dataset_root
    )

    assert report.input_image_count == 3
    assert report.mask_count == 1
    assert report.corrupt_files == []
    assert report.unsupported_files == []
    assert report.mask_association_errors == []

    assert len(records) == 4
    assert len(associations) == 1

    association = associations[0]

    assert association.image_path == "test/crack/001.png"
    assert (
        association.mask_path
        == "ground_truth/crack/001_mask.png"
    )


def test_missing_required_directory_fails(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    create_png(dataset_root / "train" / "good" / "001.png")
    create_png(dataset_root / "test" / "good" / "001.png")

    with pytest.raises(
        DatasetValidationError,
        match="Missing required dataset directories",
    ):
        validate_dataset(dataset_root)


def test_missing_mask_is_reported(tmp_path: Path) -> None:
    dataset_root = tmp_path / "tile"

    create_png(dataset_root / "train" / "good" / "001.png")
    create_png(dataset_root / "test" / "good" / "001.png")
    create_png(dataset_root / "test" / "crack" / "001.png")

    (
        dataset_root / "ground_truth" / "crack"
    ).mkdir(parents=True)

    report, _, associations = validate_dataset(
        dataset_root
    )

    assert associations == []
    assert len(report.mask_association_errors) == 1
    assert "Missing mask" in report.mask_association_errors[0]


def test_orphan_mask_is_reported(tmp_path: Path) -> None:
    dataset_root = tmp_path / "tile"
    create_minimal_valid_dataset(dataset_root)

    create_png(
        dataset_root
        / "ground_truth"
        / "crack"
        / "999_mask.png",
        mode="L",
    )

    report, _, _ = validate_dataset(dataset_root)

    assert len(report.mask_association_errors) == 1
    assert "Orphan ground-truth mask" in (
        report.mask_association_errors[0]
    )


def test_corrupt_image_is_reported(tmp_path: Path) -> None:
    dataset_root = tmp_path / "tile"
    create_minimal_valid_dataset(dataset_root)

    corrupt_path = (
        dataset_root
        / "test"
        / "crack"
        / "corrupt.png"
    )
    corrupt_path.write_bytes(b"not-an-image")

    report, _, _ = validate_dataset(dataset_root)

    assert len(report.corrupt_files) == 1
    assert "corrupt.png" in report.corrupt_files[0]


def test_unknown_file_is_reported(tmp_path: Path) -> None:
    dataset_root = tmp_path / "tile"
    create_minimal_valid_dataset(dataset_root)

    unknown_file = dataset_root / "unexpected.bin"
    unknown_file.write_bytes(b"unexpected")

    report, _, _ = validate_dataset(dataset_root)

    assert report.unsupported_files == ["unexpected.bin"]


def test_license_and_readme_are_allowed(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"
    create_minimal_valid_dataset(dataset_root)

    (dataset_root / "license.txt").write_text(
        "license",
        encoding="utf-8",
    )
    (dataset_root / "readme.txt").write_text(
        "readme",
        encoding="utf-8",
    )

    report, _, _ = validate_dataset(dataset_root)

    assert report.unsupported_files == []