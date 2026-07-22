from pathlib import Path

from PIL import Image

from ml.data.build_manifest import build_manifest


def create_png(
    path: Path,
    mode: str = "RGB",
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image = Image.new(
        mode=mode,
        size=(32, 32),
        color=0,
    )

    image.save(path, format="PNG")


def create_dataset(root: Path) -> None:
    for index in range(10):
        create_png(
            root
            / "train"
            / "good"
            / f"{index:03d}.png"
        )

    create_png(
        root / "test" / "good" / "000.png"
    )

    create_png(
        root / "test" / "crack" / "001.png"
    )

    create_png(
        root
        / "ground_truth"
        / "crack"
        / "001_mask.png",
        mode="L",
    )


def test_manifest_has_expected_splits(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"
    create_dataset(dataset_root)

    manifest = build_manifest(
        dataset_root=dataset_root,
        validation_ratio=0.2,
        random_seed=42,
    )

    split_counts = {
        split: sum(
            record.split == split
            for record in manifest.records
        )
        for split in (
            "train",
            "validation",
            "test",
        )
    }

    assert split_counts == {
        "train": 8,
        "validation": 2,
        "test": 2,
    }


def test_training_and_validation_are_normal_only(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"
    create_dataset(dataset_root)

    manifest = build_manifest(dataset_root)

    non_test_records = [
        record
        for record in manifest.records
        if record.split in {
            "train",
            "validation",
        }
    ]

    assert non_test_records

    assert all(
        record.class_name == "good"
        for record in non_test_records
    )

    assert all(
        record.label == 0
        for record in non_test_records
    )

    assert all(
        record.mask_path is None
        for record in non_test_records
    )


def test_defective_test_sample_has_mask(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"
    create_dataset(dataset_root)

    manifest = build_manifest(dataset_root)

    defective_record = next(
        record
        for record in manifest.records
        if record.class_name == "crack"
    )

    assert defective_record.split == "test"
    assert defective_record.label == 1
    assert defective_record.is_anomaly is True
    assert (
        defective_record.mask_path
        == "ground_truth/crack/001_mask.png"
    )


def test_manifest_generation_is_deterministic(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"
    create_dataset(dataset_root)

    first_manifest = build_manifest(
        dataset_root=dataset_root,
        validation_ratio=0.2,
        random_seed=42,
    )

    second_manifest = build_manifest(
        dataset_root=dataset_root,
        validation_ratio=0.2,
        random_seed=42,
    )

    assert (
        first_manifest.dataset_version
        == second_manifest.dataset_version
    )

    assert (
        first_manifest.records
        == second_manifest.records
    )


def test_different_seed_changes_validation_split(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"
    create_dataset(dataset_root)

    first_manifest = build_manifest(
        dataset_root=dataset_root,
        validation_ratio=0.2,
        random_seed=42,
    )

    second_manifest = build_manifest(
        dataset_root=dataset_root,
        validation_ratio=0.2,
        random_seed=99,
    )

    first_validation_paths = {
        record.image_path
        for record in first_manifest.records
        if record.split == "validation"
    }

    second_validation_paths = {
        record.image_path
        for record in second_manifest.records
        if record.split == "validation"
    }

    assert (
        first_validation_paths
        != second_validation_paths
    )


def test_splits_do_not_overlap(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "tile"
    create_dataset(dataset_root)

    manifest = build_manifest(dataset_root)

    paths_by_split = {
        split: {
            record.image_path
            for record in manifest.records
            if record.split == split
        }
        for split in (
            "train",
            "validation",
            "test",
        )
    }

    assert paths_by_split["train"].isdisjoint(
        paths_by_split["validation"]
    )

    assert paths_by_split["train"].isdisjoint(
        paths_by_split["test"]
    )

    assert paths_by_split["validation"].isdisjoint(
        paths_by_split["test"]
    )