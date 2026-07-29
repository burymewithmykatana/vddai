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
from ml.data.torch_dataloader import (
    DataLoaderConfig,
    collect_batch_sample_ids,
    create_split_dataloader,
    create_split_loaders,
    manifest_sample_ids,
)
from ml.data.torch_dataset import TorchManifestDataset


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
            mask.putpixel((x, y), 255)

    mask.save(path, format="PNG")


def split_record(
    name: str,
    split: str,
) -> ManifestRecord:
    prefix = {
        "train": "normal",
        "validation": "val",
        "test": "test",
    }[split]

    is_test_anomaly = split == "test" and name != "000"

    if is_test_anomaly:
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

    return ManifestRecord(
        sample_id=f"{prefix}-{name}",
        image_path=f"train/good/{name}.png",
        split=split,
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
        dataset_version="dataloader-test-version",
        random_seed=42,
        validation_ratio=0.2,
        records=records,
    )


def build_torch_dataset(
    tmp_path: Path,
    records: list[ManifestRecord],
    split: str,
) -> TorchManifestDataset:
    dataset_root = tmp_path / "tile"

    for record in records:
        create_rgb_image(dataset_root / record.image_path)

        if record.mask_path is not None:
            create_mask(dataset_root / record.mask_path)

    manifest_dataset = ManifestDataset(
        manifest=create_manifest(records),
        dataset_root=dataset_root,
        split=split,
        preprocessing_service=ImagePreprocessingService(
            target_width=16,
            target_height=12,
        ),
    )

    return TorchManifestDataset(manifest_dataset)


def build_train_dataset(
    tmp_path: Path,
    count: int = 4,
) -> TorchManifestDataset:
    records = [
        split_record(f"{index:03d}", "train")
        for index in range(1, count + 1)
    ]

    return build_torch_dataset(
        tmp_path=tmp_path,
        records=records,
        split="train",
    )


def build_split_datasets(
    tmp_path: Path,
) -> tuple[
    TorchManifestDataset,
    TorchManifestDataset,
    TorchManifestDataset,
]:
    train_records = [
        split_record("001", "train"),
        split_record("002", "train"),
    ]

    validation_records = [
        split_record("003", "validation"),
        split_record("004", "validation"),
    ]

    test_records = [
        split_record("000", "test"),
        split_record("001", "test"),
    ]

    return (
        build_torch_dataset(tmp_path, train_records, "train"),
        build_torch_dataset(tmp_path, validation_records, "validation"),
        build_torch_dataset(tmp_path, test_records, "test"),
    )


def test_same_seed_produces_same_training_order(
    tmp_path: Path,
) -> None:
    dataset = build_train_dataset(tmp_path)

    config = DataLoaderConfig(
        batch_size=2,
        random_seed=42,
    )

    first_order = collect_batch_sample_ids(
        create_split_dataloader(dataset, "train", config)
    )

    second_order = collect_batch_sample_ids(
        create_split_dataloader(dataset, "train", config)
    )

    assert first_order == second_order
    assert set(first_order) == set(
        manifest_sample_ids(dataset)
    )


def test_different_seed_changes_training_order(
    tmp_path: Path,
) -> None:
    dataset = build_train_dataset(tmp_path)

    first_order = collect_batch_sample_ids(
        create_split_dataloader(
            dataset,
            "train",
            DataLoaderConfig(
                batch_size=1,
                random_seed=42,
            ),
        )
    )

    second_order = collect_batch_sample_ids(
        create_split_dataloader(
            dataset,
            "train",
            DataLoaderConfig(
                batch_size=1,
                random_seed=99,
            ),
        )
    )

    assert first_order != second_order
    assert set(first_order) == set(
        manifest_sample_ids(dataset)
    )
    assert set(second_order) == set(
        manifest_sample_ids(dataset)
    )


def test_validation_order_matches_manifest(
    tmp_path: Path,
) -> None:
    _, validation_dataset, _ = build_split_datasets(tmp_path)

    observed_order = collect_batch_sample_ids(
        create_split_dataloader(
            validation_dataset,
            "validation",
            DataLoaderConfig(
                batch_size=2,
                random_seed=42,
            ),
        )
    )

    expected_order = manifest_sample_ids(validation_dataset)

    assert observed_order == expected_order
    assert observed_order == (
        "val-003",
        "val-004",
    )


def test_test_order_matches_manifest(
    tmp_path: Path,
) -> None:
    _, _, test_dataset = build_split_datasets(tmp_path)

    observed_order = collect_batch_sample_ids(
        create_split_dataloader(
            test_dataset,
            "test",
            DataLoaderConfig(
                batch_size=2,
                random_seed=42,
            ),
        )
    )

    expected_order = manifest_sample_ids(test_dataset)

    assert observed_order == expected_order
    assert observed_order == (
        "test-000",
        "crack-001",
    )


def test_no_samples_disappear_from_training_loader(
    tmp_path: Path,
) -> None:
    dataset = build_train_dataset(tmp_path)

    observed_ids = collect_batch_sample_ids(
        create_split_dataloader(
            dataset,
            "train",
            DataLoaderConfig(
                batch_size=3,
                random_seed=42,
            ),
        )
    )

    expected_ids = set(manifest_sample_ids(dataset))

    assert len(observed_ids) == len(dataset)
    assert set(observed_ids) == expected_ids


def test_batch_shapes_match_contract(
    tmp_path: Path,
) -> None:
    dataset = build_train_dataset(tmp_path, count=3)

    loader = create_split_dataloader(
        dataset,
        "train",
        DataLoaderConfig(
            batch_size=2,
            random_seed=42,
        ),
    )

    batch = next(iter(loader))

    assert batch.images.shape == (
        2,
        3,
        12,
        16,
    )
    assert batch.images.dtype == torch.float32

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


def test_create_split_loaders_builds_all_splits(
    tmp_path: Path,
) -> None:
    train_dataset, validation_dataset, test_dataset = (
        build_split_datasets(tmp_path)
    )

    loaders = create_split_loaders(
        train_dataset=train_dataset,
        validation_dataset=validation_dataset,
        test_dataset=test_dataset,
        config=DataLoaderConfig(
            batch_size=2,
            random_seed=42,
        ),
    )

    train_order = collect_batch_sample_ids(loaders.train)
    validation_order = collect_batch_sample_ids(loaders.validation)
    test_order = collect_batch_sample_ids(loaders.test)

    assert train_order == (
        "normal-001",
        "normal-002",
    )
    assert validation_order == (
        "val-003",
        "val-004",
    )
    assert test_order == (
        "test-000",
        "crack-001",
    )


def test_drop_last_is_configurable(
    tmp_path: Path,
) -> None:
    dataset = build_train_dataset(tmp_path, count=3)

    loader = create_split_dataloader(
        dataset,
        "train",
        DataLoaderConfig(
            batch_size=2,
            random_seed=42,
            drop_last=True,
        ),
    )

    observed_ids = collect_batch_sample_ids(loader)

    assert len(observed_ids) == 2


def test_invalid_batch_size_is_rejected(
    tmp_path: Path,
) -> None:
    dataset = build_train_dataset(tmp_path)

    with pytest.raises(
        ValueError,
        match="batch_size must be positive",
    ):
        create_split_dataloader(
            dataset,
            "train",
            DataLoaderConfig(batch_size=0),
        )
