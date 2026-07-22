from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
)
from ml.data.build_manifest import (
    DatasetManifest,
    ManifestRecord,
)
from ml.data.dataset import (
    DatasetLoadingError,
    ManifestDataset,
    collate_samples,
    preprocess_mask,
)


def create_rgb_image(
    path: Path,
    color: tuple[int, int, int] = (64, 128, 255),
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

    mask = Image.new(
        mode="L",
        size=(40, 30),
        color=0,
    )

    for x in range(10, 30):
        for y in range(5, 20):
            mask.putpixel(
                (x, y),
                255,
            )

    mask.save(
        path,
        format="PNG",
    )


def normal_record(
    name: str = "001",
) -> ManifestRecord:
    return ManifestRecord(
        sample_id=f"normal-{name}",
        image_path=f"train/good/{name}.png",
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


def anomaly_record() -> ManifestRecord:
    return ManifestRecord(
        sample_id="crack-001",
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


def create_manifest(
    records: list[ManifestRecord],
) -> DatasetManifest:
    return DatasetManifest(
        dataset_name="MVTec AD",
        category="tile",
        dataset_version="test-version",
        random_seed=42,
        validation_ratio=0.2,
        records=records,
    )


def test_mask_preprocessing_is_binary(
    tmp_path: Path,
) -> None:
    mask_path = tmp_path / "mask.png"
    create_mask(mask_path)

    mask = preprocess_mask(
        mask_path=mask_path,
        target_width=16,
        target_height=12,
    )

    assert mask.shape == (1, 12, 16)
    assert mask.dtype == np.uint8
    assert mask.flags.c_contiguous

    assert set(
        np.unique(mask).tolist()
    ).issubset({0, 1})

    assert mask.max() == 1


def test_normal_dataset_sample_has_zero_mask(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    create_rgb_image(
        dataset_root
        / "train"
        / "good"
        / "001.png"
    )

    dataset = ManifestDataset(
        manifest=create_manifest(
            [normal_record()]
        ),
        dataset_root=dataset_root,
        split="train",
        preprocessing_service=(
            ImagePreprocessingService(
                target_width=16,
                target_height=12,
            )
        ),
    )

    sample = dataset[0]

    assert sample.label == 0
    assert sample.is_anomaly is False
    assert sample.has_mask is False
    assert sample.mask_path is None

    assert sample.image.shape == (
        3,
        12,
        16,
    )

    assert sample.mask.shape == (
        1,
        12,
        16,
    )

    assert sample.mask.sum() == 0


def test_anomaly_dataset_sample_loads_mask(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    create_rgb_image(
        dataset_root
        / "test"
        / "crack"
        / "001.png"
    )

    create_mask(
        dataset_root
        / "ground_truth"
        / "crack"
        / "001_mask.png"
    )

    dataset = ManifestDataset(
        manifest=create_manifest(
            [anomaly_record()]
        ),
        dataset_root=dataset_root,
        split="test",
        preprocessing_service=(
            ImagePreprocessingService(
                target_width=16,
                target_height=12,
            )
        ),
    )

    sample = dataset[0]

    assert sample.label == 1
    assert sample.class_name == "crack"
    assert sample.is_anomaly is True
    assert sample.has_mask is True

    assert sample.mask.shape == (
        1,
        12,
        16,
    )

    assert sample.mask.max() == 1
    assert sample.mask.sum() > 0


def test_anomaly_without_mask_is_rejected(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    create_rgb_image(
        dataset_root
        / "test"
        / "crack"
        / "001.png"
    )

    invalid_record = ManifestRecord(
        sample_id="invalid",
        image_path="test/crack/001.png",
        split="test",
        label=1,
        class_name="crack",
        is_anomaly=True,
        mask_path=None,
        width=40,
        height=30,
        image_format="PNG",
        mode="RGB",
    )

    dataset = ManifestDataset(
        manifest=create_manifest(
            [invalid_record]
        ),
        dataset_root=dataset_root,
        split="test",
    )

    with pytest.raises(
        DatasetLoadingError,
        match="must have a mask",
    ):
        dataset[0]


def test_normal_sample_with_mask_is_rejected(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    create_rgb_image(
        dataset_root
        / "train"
        / "good"
        / "001.png"
    )

    invalid_record = ManifestRecord(
        sample_id="invalid-normal",
        image_path="train/good/001.png",
        split="train",
        label=0,
        class_name="good",
        is_anomaly=False,
        mask_path=(
            "ground_truth/good/001_mask.png"
        ),
        width=40,
        height=30,
        image_format="PNG",
        mode="RGB",
    )

    dataset = ManifestDataset(
        manifest=create_manifest(
            [invalid_record]
        ),
        dataset_root=dataset_root,
        split="train",
    )

    with pytest.raises(
        DatasetLoadingError,
        match="must not have a mask",
    ):
        dataset[0]


def test_dataset_rejects_empty_split(
    tmp_path: Path,
) -> None:
    manifest = create_manifest(
        [normal_record()]
    )

    with pytest.raises(
        DatasetLoadingError,
        match="no records",
    ):
        ManifestDataset(
            manifest=manifest,
            dataset_root=tmp_path,
            split="validation",
        )


def test_dataset_iteration_preserves_order(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    records = [
        normal_record("001"),
        normal_record("002"),
        normal_record("003"),
    ]

    for record in records:
        create_rgb_image(
            dataset_root / record.image_path
        )

    dataset = ManifestDataset(
        manifest=create_manifest(records),
        dataset_root=dataset_root,
        split="train",
        preprocessing_service=(
            ImagePreprocessingService(
                target_width=16,
                target_height=12,
            )
        ),
    )

    assert [
        sample.sample_id
        for sample in dataset
    ] == [
        "normal-001",
        "normal-002",
        "normal-003",
    ]


def test_collate_samples_creates_nchw_batch(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"

    records = [
        normal_record("001"),
        normal_record("002"),
    ]

    for record in records:
        create_rgb_image(
            dataset_root / record.image_path
        )

    dataset = ManifestDataset(
        manifest=create_manifest(records),
        dataset_root=dataset_root,
        split="train",
        preprocessing_service=(
            ImagePreprocessingService(
                target_width=16,
                target_height=12,
            )
        ),
    )

    batch = collate_samples(
        [
            dataset[0],
            dataset[1],
        ]
    )

    assert batch.images.shape == (
        2,
        3,
        12,
        16,
    )

    assert batch.images.dtype == np.float32
    assert batch.images.flags.c_contiguous

    assert batch.labels.shape == (2,)
    assert batch.labels.dtype == np.int64

    assert batch.masks.shape == (
        2,
        1,
        12,
        16,
    )

    assert batch.masks.dtype == np.uint8

    assert batch.has_masks.shape == (2,)
    assert batch.has_masks.dtype == np.bool_

    assert batch.sample_ids == (
        "normal-001",
        "normal-002",
    )


def test_empty_batch_is_rejected() -> None:
    with pytest.raises(
        DatasetLoadingError,
        match="zero samples",
    ):
        collate_samples([])