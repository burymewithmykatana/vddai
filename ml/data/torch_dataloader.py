"""Deterministic PyTorch DataLoader construction for VDDAI manifest datasets.

Reproducibility boundaries:

- **Sample ordering**: train shuffling and DataLoader iteration order are seeded
  and tested via stable ``sample_id`` sequences. Validation and test loaders
  preserve manifest order because ``shuffle=False``.
- **Seeded execution**: Python ``random``, NumPy, PyTorch, the DataLoader
  ``generator``, and worker processes (when ``num_workers > 0``) receive
  deterministic seeds.
- **Numerical kernels**: PyTorch does not guarantee fully deterministic
  behaviour for every GPU/CPU kernel. This module does not claim bitwise-stable
  forward-pass outputs—only deterministic loader ordering under the configured
  seed.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import torch
from torch.utils.data import DataLoader

from ml.data.torch_dataset import (
    DEFAULT_RANDOM_SEED,
    TorchManifestDataset,
    collate_torch_samples,
)

SplitName = Literal["train", "validation", "test"]

SHUFFLE_BY_SPLIT: dict[SplitName, bool] = {
    "train": True,
    "validation": False,
    "test": False,
}


@dataclass(frozen=True)
class DataLoaderConfig:
    """Configuration boundary for VDDAI PyTorch DataLoaders.

    ``drop_last`` defaults to ``False`` so every manifest sample remains
    observable unless a training caller explicitly opts into dropping a
    partial final batch.
    """

    batch_size: int
    random_seed: int = DEFAULT_RANDOM_SEED
    num_workers: int = 0
    pin_memory: bool = False
    drop_last: bool = False


@dataclass(frozen=True)
class SplitDataLoaders:
    train: DataLoader
    validation: DataLoader
    test: DataLoader


def seed_execution(random_seed: int) -> torch.Generator:
    """Seed Python, NumPy, and PyTorch and return a DataLoader generator."""
    random.seed(random_seed)
    np.random.seed(random_seed)
    torch.manual_seed(random_seed)

    generator = torch.Generator()
    generator.manual_seed(random_seed)
    return generator


def _worker_init_fn(worker_id: int, base_seed: int) -> None:
    worker_seed = base_seed + worker_id
    random.seed(worker_seed)
    np.random.seed(worker_seed)
    torch.manual_seed(worker_seed)


WorkerInitFn = Callable[[int], None]


def _make_worker_init_fn(base_seed: int) -> WorkerInitFn:
    def init_fn(worker_id: int) -> None:
        _worker_init_fn(worker_id, base_seed)

    return init_fn


def create_split_dataloader(
    dataset: TorchManifestDataset,
    split: SplitName,
    config: DataLoaderConfig,
) -> DataLoader:
    """Build a DataLoader for one manifest split with seeded ordering."""
    if config.batch_size <= 0:
        raise ValueError("batch_size must be positive.")

    if config.num_workers < 0:
        raise ValueError("num_workers must be non-negative.")

    generator = seed_execution(config.random_seed)
    shuffle = SHUFFLE_BY_SPLIT[split]

    worker_init = None
    if config.num_workers > 0:
        worker_init = _make_worker_init_fn(config.random_seed)

    return DataLoader(
        dataset=dataset,
        batch_size=config.batch_size,
        shuffle=shuffle,
        num_workers=config.num_workers,
        collate_fn=collate_torch_samples,
        generator=generator,
        drop_last=config.drop_last,
        pin_memory=config.pin_memory,
        worker_init_fn=worker_init,
    )


def create_split_loaders(
    train_dataset: TorchManifestDataset,
    validation_dataset: TorchManifestDataset,
    test_dataset: TorchManifestDataset,
    config: DataLoaderConfig,
) -> SplitDataLoaders:
    """Build train, validation, and test DataLoaders from one configuration."""
    return SplitDataLoaders(
        train=create_split_dataloader(
            train_dataset,
            "train",
            config,
        ),
        validation=create_split_dataloader(
            validation_dataset,
            "validation",
            config,
        ),
        test=create_split_dataloader(
            test_dataset,
            "test",
            config,
        ),
    )


def collect_batch_sample_ids(loader: DataLoader) -> tuple[str, ...]:
    """Return the sample_id sequence emitted by a DataLoader."""
    sample_ids: list[str] = []

    for batch in loader:
        sample_ids.extend(batch.sample_ids)

    return tuple(sample_ids)


def manifest_sample_ids(dataset: TorchManifestDataset) -> tuple[str, ...]:
    """Return manifest-order sample identifiers for a torch dataset."""
    return tuple(
        record.sample_id
        for record in dataset.dataset.records
    )
