"""Thin PyTorch adapter over the framework-independent manifest dataset.

The adapter converts validated NumPy samples into tensors without redefining
dataset semantics or applying additional image preprocessing. Pixel values remain
in the shared ``[0, 1]`` contract produced by ``ImagePreprocessingService``.

Mask tensors use ``torch.uint8`` to stay aligned with the NumPy batch contract
(``uint8`` values in ``{0, 1}``). ``has_mask`` uses ``torch.bool``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch
from torch import Tensor
from torch.utils.data import DataLoader, Dataset

from ml.data.dataset import DatasetSample, ManifestDataset

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


def _tensor_from_numpy(array) -> Tensor:
    """Convert a C-contiguous NumPy array to a tensor without copying."""
    tensor = torch.from_numpy(array)

    if not tensor.is_contiguous():
        tensor = tensor.contiguous()

    return tensor


def convert_sample(sample: DatasetSample) -> TorchDatasetSample:
    image = _tensor_from_numpy(sample.image)

    if image.dtype != torch.float32:
        raise TorchDatasetError("Model input must use torch.float32.")

    if image.ndim != 3 or image.shape[0] != 3:
        raise TorchDatasetError("Model input must have shape (3, H, W).")

    mask = _tensor_from_numpy(sample.mask)

    if mask.dtype != torch.uint8:
        raise TorchDatasetError("Segmentation mask must use torch.uint8.")

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
    num_workers: int = 0,
    pin_memory: bool = False,
    drop_last: bool = False,
) -> DataLoader:
    """Backward-compatible wrapper around the split-aware loader factory."""
    from ml.data.torch_dataloader import (
        DataLoaderConfig,
        create_split_dataloader,
    )

    split = dataset.dataset.split

    if split not in {"train", "validation", "test"}:
        raise ValueError(
            "dataset split must be one of: train, validation, test"
        )

    config = DataLoaderConfig(
        batch_size=batch_size,
        random_seed=random_seed,
        num_workers=num_workers,
        pin_memory=pin_memory,
        drop_last=drop_last,
    )

    return create_split_dataloader(
        dataset=dataset,
        split=split,  # type: ignore[arg-type]
        config=config,
    )
