from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
)
from ml.data.build_manifest import (
    DatasetManifest,
    ManifestRecord,
)
from ml.data.dataset import ManifestDataset
from ml.data.torch_dataset import (
    TorchDatasetError,
    TorchManifestDataset,
    collate_torch_samples,
    convert_sample,
    create_dataloader,
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


def normal_record(name: str) -> ManifestRecord:
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


def anomaly_record(name: str = "001") -> ManifestRecord:
    return ManifestRecord(
        sample_id=f"crack-{name}",
        image_path=f"test/crack/{name}.png",
        split="test",
        label=1,
        class_name="crack",
        is_anomaly=True,
        mask_path=f"ground_truth/crack/{name}_mask.png",
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
        dataset_version="torch-test-version",
        random_seed=42,
        validation_ratio=0.2,
        records=records,
    )


def create_manifest_dataset(
    tmp_path: Path,
    records: list[ManifestRecord],
    split: str,
) -> ManifestDataset:
    dataset_root = tmp_path / "tile"

    for record in records:
        create_rgb_image(
            dataset_root / record.image_path,
            color=(64, 128, 255),
        )

        if record.mask_path is not None:
            create_mask(dataset_root / record.mask_path)

    return ManifestDataset(
        manifest=create_manifest(records),
        dataset_root=dataset_root,
        split=split,
        preprocessing_service=ImagePreprocessingService(
            target_width=16,
            target_height=12,
        ),
    )


def create_torch_dataset(
    tmp_path: Path,
) -> TorchManifestDataset:
    records = [
        normal_record("001"),
        normal_record("002"),
    ]

    manifest_dataset = create_manifest_dataset(
        tmp_path=tmp_path,
        records=records,
        split="train",
    )

    return TorchManifestDataset(manifest_dataset)


def test_torch_sample_satisfies_tensor_contract(
    tmp_path: Path,
) -> None:
    dataset = create_torch_dataset(tmp_path)

    sample = dataset[0]

    assert sample.sample_id == "normal-001"
    assert sample.split == "train"
    assert sample.source_path == "train/good/001.png"
    assert sample.class_name == "good"
    assert sample.mask_path is None

    assert sample.image.shape == (
        3,
        12,
        16,
    )

    assert sample.image.dtype == torch.float32
    assert sample.image.is_contiguous()
    assert torch.isfinite(sample.image).all()
    assert sample.image.min().item() >= 0.0
    assert sample.image.max().item() <= 1.0

    assert sample.label.shape == ()
    assert sample.label.dtype == torch.int64
    assert sample.label.item() == 0

    assert sample.mask.shape == (
        1,
        12,
        16,
    )

    assert sample.mask.dtype == torch.uint8
    assert sample.mask.sum().item() == 0

    assert sample.has_mask.shape == ()
    assert sample.has_mask.dtype == torch.bool
    assert sample.has_mask.item() is False


def test_anomaly_sample_loads_mask(
    tmp_path: Path,
) -> None:
    records = [anomaly_record()]

    manifest_dataset = create_manifest_dataset(
        tmp_path=tmp_path,
        records=records,
        split="test",
    )

    dataset = TorchManifestDataset(manifest_dataset)
    sample = dataset[0]

    assert sample.sample_id == "crack-001"
    assert sample.source_path == "test/crack/001.png"
    assert sample.class_name == "crack"
    assert sample.mask_path == "ground_truth/crack/001_mask.png"
    assert sample.label.item() == 1
    assert sample.has_mask.item() is True

    assert sample.mask.dtype == torch.uint8
    assert sample.mask.shape == (1, 12, 16)
    assert sample.mask.max().item() == 1
    assert sample.mask.sum().item() > 0


def test_conversion_does_not_mutate_numpy_sample(
    tmp_path: Path,
) -> None:
    manifest_dataset = create_manifest_dataset(
        tmp_path=tmp_path,
        records=[normal_record("001")],
        split="train",
    )

    numpy_sample = manifest_dataset[0]
    image_before = numpy_sample.image.copy()
    mask_before = numpy_sample.mask.copy()

    convert_sample(numpy_sample)

    assert np.array_equal(numpy_sample.image, image_before)
    assert np.array_equal(numpy_sample.mask, mask_before)


def test_dataloader_preserves_manifest_order(
    tmp_path: Path,
) -> None:
    dataset = create_torch_dataset(tmp_path)

    dataloader = create_dataloader(
        dataset=dataset,
        batch_size=2,
    )

    batch = next(iter(dataloader))

    assert batch.sample_ids == (
        "normal-001",
        "normal-002",
    )

    assert batch.source_paths == (
        "train/good/001.png",
        "train/good/002.png",
    )

    assert batch.class_names == (
        "good",
        "good",
    )

    assert batch.images.shape == (
        2,
        3,
        12,
        16,
    )

    assert batch.images.dtype == torch.float32
    assert batch.images.is_contiguous()

    assert batch.labels.shape == (2,)
    assert batch.labels.dtype == torch.int64

    assert batch.masks.shape == (
        2,
        1,
        12,
        16,
    )

    assert batch.masks.dtype == torch.uint8

    assert batch.has_masks.shape == (2,)
    assert batch.has_masks.dtype == torch.bool


def test_dataloader_is_deterministic(
    tmp_path: Path,
) -> None:
    dataset = create_torch_dataset(tmp_path)

    first_loader = create_dataloader(
        dataset=dataset,
        batch_size=2,
        random_seed=42,
    )

    second_loader = create_dataloader(
        dataset=dataset,
        batch_size=2,
        random_seed=42,
    )

    first_batch = next(iter(first_loader))
    second_batch = next(iter(second_loader))

    assert first_batch.sample_ids == second_batch.sample_ids

    assert torch.equal(
        first_batch.images,
        second_batch.images,
    )

    assert torch.equal(
        first_batch.labels,
        second_batch.labels,
    )

    assert torch.equal(
        first_batch.masks,
        second_batch.masks,
    )


def test_dataset_iteration_is_repeatable(
    tmp_path: Path,
) -> None:
    dataset = create_torch_dataset(tmp_path)

    first_pass = [
        sample.sample_id
        for sample in (dataset[index] for index in range(len(dataset)))
    ]

    second_pass = [
        sample.sample_id
        for sample in (dataset[index] for index in range(len(dataset)))
    ]

    assert first_pass == second_pass == [
        "normal-001",
        "normal-002",
    ]


def test_empty_torch_batch_is_rejected() -> None:
    with pytest.raises(
        TorchDatasetError,
        match="zero samples",
    ):
        collate_torch_samples([])


def test_dataloader_rejects_invalid_batch_size(
    tmp_path: Path,
) -> None:
    dataset = create_torch_dataset(tmp_path)

    with pytest.raises(
        ValueError,
        match="batch_size must be positive",
    ):
        create_dataloader(
            dataset=dataset,
            batch_size=0,
        )
