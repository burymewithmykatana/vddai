from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
)
from ml.data.build_manifest import ManifestRecord
from ml.data.process_manifest import (
    ManifestProcessingError,
    process_manifest_record,
    resolve_manifest_path,
)


def create_image(
    path: Path,
    size: tuple[int, int] = (40, 30),
    color: tuple[int, int, int] = (64, 128, 255),
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image = Image.new(
        mode="RGB",
        size=size,
        color=color,
    )

    image.save(path, format="PNG")


def create_record(
    image_path: str = "train/good/001.png",
) -> ManifestRecord:
    return ManifestRecord(
        sample_id="sample-001",
        image_path=image_path,
        split="train",
        label=0,
        class_name="good",
        is_anomaly=False,
        mask_path=None,
        width=40,
        height=30,
        image_format="PNG",
        mode="RGB",
    )


def test_resolve_manifest_path_returns_local_file(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"
    image_path = (
        dataset_root
        / "train"
        / "good"
        / "001.png"
    )

    create_image(image_path)

    resolved = resolve_manifest_path(
        dataset_root=dataset_root,
        relative_path="train/good/001.png",
    )

    assert resolved == image_path.resolve()


def test_absolute_manifest_path_is_rejected(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"
    outside_file = tmp_path / "outside.png"

    create_image(outside_file)

    with pytest.raises(
        ManifestProcessingError,
        match="must be relative",
    ):
        resolve_manifest_path(
            dataset_root=dataset_root,
            relative_path=str(outside_file.resolve()),
        )


def test_path_traversal_is_rejected(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"
    outside_file = tmp_path / "outside.png"

    dataset_root.mkdir(parents=True)
    create_image(outside_file)

    with pytest.raises(
        ManifestProcessingError,
        match="escapes the dataset root",
    ):
        resolve_manifest_path(
            dataset_root=dataset_root,
            relative_path="../outside.png",
        )


def test_missing_manifest_image_is_rejected(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"
    dataset_root.mkdir(parents=True)

    with pytest.raises(
        ManifestProcessingError,
        match="does not exist",
    ):
        resolve_manifest_path(
            dataset_root=dataset_root,
            relative_path="train/good/missing.png",
        )


def test_manifest_record_is_processed(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    create_image(
        dataset_root
        / "train"
        / "good"
        / "001.png"
    )

    service = ImagePreprocessingService(
        target_width=32,
        target_height=24,
    )

    sample = process_manifest_record(
        record=create_record(),
        dataset_root=dataset_root,
        preprocessing_service=service,
    )

    assert sample.sample_id == "sample-001"
    assert sample.split == "train"
    assert sample.label == 0
    assert sample.class_name == "good"
    assert sample.is_anomaly is False
    assert sample.source_path == "train/good/001.png"

    assert sample.original_width == 40
    assert sample.original_height == 30

    assert sample.model_input.shape == (
        3,
        24,
        32,
    )

    assert sample.model_input.dtype == np.float32
    assert sample.model_input.flags.c_contiguous
    assert sample.model_input.min() >= 0.0
    assert sample.model_input.max() <= 1.0


def test_processing_is_deterministic(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    create_image(
        dataset_root
        / "train"
        / "good"
        / "001.png"
    )

    service = ImagePreprocessingService(
        target_width=32,
        target_height=24,
    )

    first_sample = process_manifest_record(
        record=create_record(),
        dataset_root=dataset_root,
        preprocessing_service=service,
    )

    second_sample = process_manifest_record(
        record=create_record(),
        dataset_root=dataset_root,
        preprocessing_service=service,
    )

    np.testing.assert_array_equal(
        first_sample.model_input,
        second_sample.model_input,
    )


def test_corrupt_manifest_image_is_rejected(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    corrupt_path = (
        dataset_root
        / "train"
        / "good"
        / "001.png"
    )

    corrupt_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    corrupt_path.write_bytes(b"not-an-image")

    with pytest.raises(
        ManifestProcessingError,
        match="could not be preprocessed",
    ):
        process_manifest_record(
            record=create_record(),
            dataset_root=dataset_root,
        )


def test_manifest_metadata_is_preserved_for_anomaly(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    create_image(
        dataset_root
        / "test"
        / "crack"
        / "001.png"
    )

    record = ManifestRecord(
        sample_id="defect-001",
        image_path="test/crack/001.png",
        split="test",
        label=1,
        class_name="crack",
        is_anomaly=True,
        mask_path=(
            "ground_truth/crack/001_mask.png"
        ),
        width=40,
        height=30,
        image_format="PNG",
        mode="RGB",
    )

    sample = process_manifest_record(
        record=record,
        dataset_root=dataset_root,
        preprocessing_service=(
            ImagePreprocessingService(
                target_width=32,
                target_height=32,
            )
        ),
    )

    assert sample.sample_id == "defect-001"
    assert sample.split == "test"
    assert sample.label == 1
    assert sample.class_name == "crack"
    assert sample.is_anomaly is True