from pathlib import Path

import numpy as np
from PIL import Image

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
)
from ml.data.report import (
    build_pipeline_report,
    write_pipeline_report,
)


def create_rgb_image(
    path: Path,
    color: tuple[int, int, int],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    Image.new(
        mode="RGB",
        size=(40, 30),
        color=color,
    ).save(
        path,
        format="PNG",
    )


def create_mask(path: Path) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    array = np.zeros(
        (30, 40),
        dtype=np.uint8,
    )

    array[5:20, 10:30] = 255

    Image.fromarray(
        array,
        mode="L",
    ).save(
        path,
        format="PNG",
    )


def create_miniature_mvtec_dataset(
    dataset_root: Path,
) -> None:
    # Required top-level directories.
    (dataset_root / "train").mkdir(
        parents=True
    )
    (dataset_root / "test").mkdir(
        parents=True
    )
    (dataset_root / "ground_truth").mkdir(
        parents=True
    )

    # Five normal training images:
    # ratio 0.2 creates four train and one validation.
    for index in range(5):
        create_rgb_image(
            dataset_root
            / "train"
            / "good"
            / f"{index:03d}.png",
            color=(
                20 + index,
                100,
                180,
            ),
        )

    create_rgb_image(
        dataset_root
        / "test"
        / "good"
        / "000.png",
        color=(50, 120, 200),
    )

    create_rgb_image(
        dataset_root
        / "test"
        / "crack"
        / "001.png",
        color=(180, 80, 40),
    )

    create_mask(
        dataset_root
        / "ground_truth"
        / "crack"
        / "001_mask.png"
    )


def test_complete_dataset_pipeline_report(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    create_miniature_mvtec_dataset(
        dataset_root
    )

    report = build_pipeline_report(
        dataset_root=dataset_root,
        validation_ratio=0.2,
        random_seed=42,
        preprocessing_service=(
            ImagePreprocessingService(
                target_width=16,
                target_height=12,
            )
        ),
    )

    assert report.input_image_count == 7
    assert report.mask_count == 1
    assert report.manifest_record_count == 7

    assert report.split_counts == {
        "test": 2,
        "train": 4,
        "validation": 1,
    }

    assert report.anomaly_counts == {
        "test/anomaly": 1,
        "test/normal": 1,
        "train/normal": 4,
        "validation/normal": 1,
    }

    assert report.mask_counts_by_split == {
        "test": 1,
    }

    assert report.corrupt_file_count == 0
    assert report.unsupported_file_count == 0
    assert (
        report.mask_association_error_count
        == 0
    )

    assert report.preprocessing_width == 16
    assert report.preprocessing_height == 12

    assert (
        report.batch_contract.images_shape
        == (2, 3, 12, 16)
    )

    assert (
        report.batch_contract.images_dtype
        == "float32"
    )

    assert (
        report.batch_contract.labels_shape
        == (2,)
    )

    assert (
        report.batch_contract.labels_dtype
        == "int64"
    )

    assert (
        report.batch_contract.masks_shape
        == (2, 1, 12, 16)
    )

    assert (
        report.batch_contract.masks_dtype
        == "uint8"
    )

    assert (
        report.batch_contract.has_masks_shape
        == (2,)
    )

    assert (
        report.batch_contract.has_masks_dtype
        == "bool"
    )


def test_pipeline_report_is_reproducible(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    create_miniature_mvtec_dataset(
        dataset_root
    )

    service = ImagePreprocessingService(
        target_width=16,
        target_height=12,
    )

    first_report = build_pipeline_report(
        dataset_root=dataset_root,
        random_seed=42,
        preprocessing_service=service,
    )

    second_report = build_pipeline_report(
        dataset_root=dataset_root,
        random_seed=42,
        preprocessing_service=service,
    )

    assert (
        first_report.dataset_version
        == second_report.dataset_version
    )

    assert (
        first_report.split_counts
        == second_report.split_counts
    )

    assert (
        first_report.batch_contract
        == second_report.batch_contract
    )


def test_pipeline_report_can_be_written(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    create_miniature_mvtec_dataset(
        dataset_root
    )

    report = build_pipeline_report(
        dataset_root=dataset_root,
        preprocessing_service=(
            ImagePreprocessingService(
                target_width=16,
                target_height=12,
            )
        ),
    )

    output_path = (
        tmp_path
        / "reports"
        / "pipeline.json"
    )

    write_pipeline_report(
        report=report,
        output_path=output_path,
    )

    content = output_path.read_text(
        encoding="utf-8"
    )

    assert output_path.is_file()
    assert report.dataset_version in content
    assert '"input_image_count": 7' in content
    assert '"images_dtype": "float32"' in content