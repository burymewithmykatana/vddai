from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch
from torch import Tensor
from torch.utils.data import DataLoader, Dataset

from ml.data.dataset import DatasetSample, ManifestDataset

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
DEFAULT_RANDOM_SEED = 42


class TorchDatasetError(RuntimeError):
    """Raised when NumPy samples cannot satisfy the PyTorch contract."""


@dataclass(frozen=True)
class TorchDatasetSample:
    sample_id: str
    split: str
    source_path: str
    class_name: str
    mask_path: str | None
    image: Tensor
    label: Tensor
    mask: Tensor
    has_mask: Tensor


@dataclass(frozen=True)
class TorchDatasetBatch:
    sample_ids: tuple[str, ...]
    splits: tuple[str, ...]
    source_paths: tuple[str, ...]
    class_names: tuple[str, ...]
    mask_paths: tuple[str | None, ...]
    images: Tensor
    labels: Tensor
    masks: Tensor
    has_masks: Tensor


def normalize_for_resnet(image: Tensor) -> Tensor:
    if image.dtype != torch.float32:
        raise TorchDatasetError("Model input must use torch.float32.")

    if image.ndim != 3 or image.shape[0] != 3:
        raise TorchDatasetError("Model input must have shape (3, H, W).")

    if not torch.isfinite(image).all():
        raise TorchDatasetError("Model input must contain only finite values.")

    if image.min().item() < 0.0 or image.max().item() > 1.0:
        raise TorchDatasetError(
            "Model input must be in the range [0, 1] " "before ImageNet normalization."
        )

    mean = image.new_tensor(IMAGENET_MEAN).view(3, 1, 1)
    std = image.new_tensor(IMAGENET_STD).view(3, 1, 1)

    return ((image - mean) / std).contiguous()


def convert_sample(sample: DatasetSample) -> TorchDatasetSample:
    image = torch.from_numpy(sample.image).clone()
    mask = torch.from_numpy(sample.mask).clone()

    image = normalize_for_resnet(image)

    mask = mask.to(dtype=torch.uint8).contiguous()

    if mask.ndim != 3 or mask.shape[0] != 1:
        raise TorchDatasetError("Segmentation mask must have shape (1, H, W).")

    return TorchDatasetSample(
        sample_id=sample.sample_id,
        split=sample.split,
        source_path=sample.source_path,
        class_name=sample.class_name,
        mask_path=sample.mask_path,
        image=image,
        label=torch.tensor(
            sample.label,
            dtype=torch.int64,
        ),
        mask=mask,
        has_mask=torch.tensor(
            sample.has_mask,
            dtype=torch.bool,
        ),
    )


class TorchManifestDataset(Dataset[TorchDatasetSample]):
    def __init__(self, dataset: ManifestDataset) -> None:
        self.dataset = dataset

    def __len__(self) -> int:
        return len(self.dataset)

    def __getitem__(self, index: int) -> TorchDatasetSample:
        return convert_sample(self.dataset[index])


def collate_torch_samples(
    samples: Sequence[TorchDatasetSample],
) -> TorchDatasetBatch:
    if not samples:
        raise TorchDatasetError("Cannot create a batch from zero samples.")

    images = torch.stack([sample.image for sample in samples]).contiguous()

    labels = torch.stack([sample.label for sample in samples]).contiguous()

    masks = torch.stack([sample.mask for sample in samples]).contiguous()

    has_masks = torch.stack([sample.has_mask for sample in samples]).contiguous()

    if images.ndim != 4:
        raise TorchDatasetError("Batch images must use NCHW layout.")

    if masks.ndim != 4:
        raise TorchDatasetError("Batch masks must use NCHW layout.")

    return TorchDatasetBatch(
        sample_ids=tuple(sample.sample_id for sample in samples),
        splits=tuple(sample.split for sample in samples),
        source_paths=tuple(sample.source_path for sample in samples),
        class_names=tuple(sample.class_name for sample in samples),
        mask_paths=tuple(sample.mask_path for sample in samples),
        images=images,
        labels=labels,
        masks=masks,
        has_masks=has_masks,
    )


def create_dataloader(
    dataset: TorchManifestDataset,
    batch_size: int,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> DataLoader:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive.")

    generator = torch.Generator()
    generator.manual_seed(random_seed)

    return DataLoader(
        dataset=dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=collate_torch_samples,
        generator=generator,
        drop_last=False,
        pin_memory=False,
    )
