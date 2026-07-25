from pathlib import Path

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
    IMAGENET_MEAN,
    TorchDatasetError,
    TorchManifestDataset,
    collate_torch_samples,
    create_dataloader,
    normalize_for_resnet,
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


def create_torch_dataset(
    tmp_path: Path,
) -> TorchManifestDataset:
    dataset_root = tmp_path / "tile"

    records = [
        normal_record("001"),
        normal_record("002"),
    ]

    create_rgb_image(
        dataset_root / records[0].image_path,
        color=(64, 128, 255),
    )

    create_rgb_image(
        dataset_root / records[1].image_path,
        color=(128, 64, 32),
    )

    manifest_dataset = ManifestDataset(
        manifest=create_manifest(records),
        dataset_root=dataset_root,
        split="train",
        preprocessing_service=ImagePreprocessingService(
            target_width=16,
            target_height=12,
        ),
    )

    return TorchManifestDataset(manifest_dataset)


def test_resnet_normalization_centers_mean_values() -> None:
    image = torch.empty(
        (3, 2, 2),
        dtype=torch.float32,
    )

    for channel, mean in enumerate(IMAGENET_MEAN):
        image[channel].fill_(mean)

    normalized = normalize_for_resnet(image)

    assert normalized.shape == (3, 2, 2)
    assert normalized.dtype == torch.float32
    assert normalized.is_contiguous()

    assert torch.allclose(
        normalized,
        torch.zeros_like(normalized),
        atol=1e-6,
    )


def test_resnet_normalization_rejects_invalid_range() -> None:
    image = torch.full(
        (3, 2, 2),
        fill_value=1.1,
        dtype=torch.float32,
    )

    with pytest.raises(
        TorchDatasetError,
        match=r"range \[0, 1\]",
    ):
        normalize_for_resnet(image)


def test_torch_sample_satisfies_tensor_contract(
    tmp_path: Path,
) -> None:
    dataset = create_torch_dataset(tmp_path)

    sample = dataset[0]

    assert sample.sample_id == "normal-001"
    assert sample.split == "train"
    assert sample.class_name == "good"

    assert sample.image.shape == (
        3,
        12,
        16,
    )

    assert sample.image.dtype == torch.float32
    assert sample.image.is_contiguous()
    assert torch.isfinite(sample.image).all()

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
