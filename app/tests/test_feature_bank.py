import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image
from torch import Tensor

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
)
from ml.data.build_manifest import (
    DatasetManifest,
    ManifestRecord,
    read_json_manifest,
)
from ml.data.torch_dataloader import DataLoaderConfig
from ml.generate_feature_bank import (
    FEATURE_BANK_CODE_VERSION,
    FEATURE_BANK_SCHEMA_VERSION,
    FeatureBankError,
    FeatureExtractorMetadata,
    calculate_manifest_fingerprint,
    generate_training_feature_bank,
)


class FakeFeatureExtractor:
    feature_dim = 3

    def extract(self, images: Tensor) -> Tensor:
        return images.mean(dim=(2, 3))


class NonFiniteFeatureExtractor:
    feature_dim = 3

    def extract(self, images: Tensor) -> Tensor:
        features = images.mean(dim=(2, 3))
        features[0, 0] = torch.nan
        return features


class WrongDimensionFeatureExtractor:
    feature_dim = 3

    def extract(self, images: Tensor) -> Tensor:
        return torch.zeros(
            (images.shape[0], 2),
            dtype=torch.float32,
        )


FAKE_EXTRACTOR_METADATA = FeatureExtractorMetadata(
    name="test.fake_mean",
    pretrained_weights="none",
    feature_layer="channel_mean",
    feature_dimension=3,
    normalization_mean=(0.0, 0.0, 0.0),
    normalization_std=(1.0, 1.0, 1.0),
)
FIXED_CREATED_AT = datetime(
    2026,
    7,
    29,
    12,
    30,
    tzinfo=timezone.utc,
)


def create_rgb_image(
    path: Path,
    color: tuple[int, int, int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(
        mode="RGB",
        size=(12, 10),
        color=color,
    ).save(path, format="PNG")


def create_record(
    sample_id: str,
    image_path: str,
    split: str,
    *,
    is_anomaly: bool = False,
) -> ManifestRecord:
    return ManifestRecord(
        sample_id=sample_id,
        image_path=image_path,
        split=split,
        label=int(is_anomaly),
        class_name="crack" if is_anomaly else "good",
        is_anomaly=is_anomaly,
        mask_path=(
            f"ground_truth/crack/{sample_id}_mask.png"
            if is_anomaly
            else None
        ),
        width=12,
        height=10,
        image_format="PNG",
        mode="RGB",
    )


def create_fake_manifest_dataset(
    tmp_path: Path,
) -> tuple[DatasetManifest, Path]:
    dataset_root = tmp_path / "tile"
    records = [
        create_record(
            "train-001",
            "train/good/001.png",
            "train",
        ),
        create_record(
            "train-002",
            "train/good/002.png",
            "train",
        ),
        create_record(
            "train-003",
            "train/good/003.png",
            "train",
        ),
        create_record(
            "train-004",
            "train/good/004.png",
            "train",
        ),
        create_record(
            "validation-001",
            "train/good/005.png",
            "validation",
        ),
        create_record(
            "test-001",
            "test/good/001.png",
            "test",
        ),
    ]
    colors = [
        (10, 20, 30),
        (40, 50, 60),
        (70, 80, 90),
        (100, 110, 120),
        (130, 140, 150),
        (160, 170, 180),
    ]

    for record, color in zip(records, colors, strict=True):
        create_rgb_image(
            dataset_root / record.image_path,
            color,
        )

    manifest = DatasetManifest(
        dataset_name="fake",
        category="tile",
        dataset_version="fake-dataset-v1",
        random_seed=42,
        validation_ratio=0.2,
        records=records,
    )
    return manifest, dataset_root


def generate_fake_bank(
    *,
    manifest: DatasetManifest,
    dataset_root: Path,
    artifact_dir: Path,
    random_seed: int = 42,
):
    return generate_training_feature_bank(
        manifest=manifest,
        dataset_root=dataset_root,
        artifact_dir=artifact_dir,
        dataloader_config=DataLoaderConfig(
            batch_size=2,
            random_seed=random_seed,
        ),
        feature_extractor=FakeFeatureExtractor(),
        extractor_metadata=FAKE_EXTRACTOR_METADATA,
        preprocessing_service=ImagePreprocessingService(
            target_width=8,
            target_height=6,
        ),
        created_at=FIXED_CREATED_AT,
    )


def test_feature_bank_preserves_row_mapping_and_metadata(
    tmp_path: Path,
) -> None:
    manifest, dataset_root = create_fake_manifest_dataset(
        tmp_path
    )

    artifact = generate_fake_bank(
        manifest=manifest,
        dataset_root=dataset_root,
        artifact_dir=tmp_path / "artifacts" / "bank",
    )

    with np.load(
        artifact.features_path,
        allow_pickle=False,
    ) as archive:
        features = archive["features"]
        sample_ids = archive["sample_ids"].tolist()
        source_paths = archive["source_paths"].tolist()
        splits = archive["splits"].tolist()
        dataset_versions = archive["dataset_versions"].tolist()

    assert features.shape == (4, 3)
    assert features.dtype == np.float32
    assert np.isfinite(features).all()
    assert len(set(sample_ids)) == 4
    assert set(sample_ids) == {
        "train-001",
        "train-002",
        "train-003",
        "train-004",
    }
    assert not {
        "validation-001",
        "test-001",
    }.intersection(sample_ids)

    expected_paths = {
        record.sample_id: record.image_path
        for record in manifest.records
        if record.split == "train"
    }
    assert [
        expected_paths[sample_id]
        for sample_id in sample_ids
    ] == source_paths
    assert splits == ["train"] * 4
    assert dataset_versions == ["fake-dataset-v1"] * 4

    metadata = json.loads(
        artifact.metadata_path.read_text(encoding="utf-8")
    )
    assert metadata["schema_version"] == (
        FEATURE_BANK_SCHEMA_VERSION
    )
    assert metadata["code_version"] == FEATURE_BANK_CODE_VERSION
    assert metadata["created_at"] == "2026-07-29T12:30:00Z"
    assert metadata["sample_count"] == 4
    assert metadata["split"] == "train"
    assert metadata["dataset_version"] == "fake-dataset-v1"
    assert metadata["manifest_fingerprint"] == (
        calculate_manifest_fingerprint(manifest)
    )
    assert metadata["random_seed"] == 42
    assert metadata["image_size"] == {
        "height": 6,
        "width": 8,
    }
    assert metadata["feature_extractor"] == {
        "name": "test.fake_mean",
        "pretrained_weights": "none",
        "feature_layer": "channel_mean",
        "feature_dimension": 3,
        "normalization": {
            "operation": "channelwise_standardization",
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
        },
    }

    expected_checksum = "sha256:" + hashlib.sha256(
        artifact.features_path.read_bytes()
    ).hexdigest()
    assert metadata["files"]["features"] == {
        "path": "features.npz",
        "sha256": expected_checksum,
    }
    assert not list(artifact.artifact_dir.glob(".*.tmp"))


def test_same_seed_produces_same_order_and_features(
    tmp_path: Path,
) -> None:
    manifest, dataset_root = create_fake_manifest_dataset(
        tmp_path
    )

    first = generate_fake_bank(
        manifest=manifest,
        dataset_root=dataset_root,
        artifact_dir=tmp_path / "first",
        random_seed=17,
    )
    second = generate_fake_bank(
        manifest=manifest,
        dataset_root=dataset_root,
        artifact_dir=tmp_path / "second",
        random_seed=17,
    )

    with np.load(first.features_path) as first_archive:
        first_features = first_archive["features"]
    with np.load(second.features_path) as second_archive:
        second_features = second_archive["features"]

    assert first.sample_ids == second.sample_ids
    assert np.array_equal(first_features, second_features)


def test_anomalous_training_record_is_rejected(
    tmp_path: Path,
) -> None:
    manifest, dataset_root = create_fake_manifest_dataset(
        tmp_path
    )
    anomalous_record = create_record(
        "bad-train",
        "train/crack/001.png",
        "train",
        is_anomaly=True,
    )
    manifest.records.append(anomalous_record)

    with pytest.raises(
        FeatureBankError,
        match="must all be normal",
    ):
        generate_fake_bank(
            manifest=manifest,
            dataset_root=dataset_root,
            artifact_dir=tmp_path / "rejected",
        )

    assert not (tmp_path / "rejected").exists()


def test_duplicate_training_sample_id_is_rejected(
    tmp_path: Path,
) -> None:
    manifest, dataset_root = create_fake_manifest_dataset(
        tmp_path
    )
    manifest.records[1] = create_record(
        "train-001",
        "train/good/002.png",
        "train",
    )

    with pytest.raises(
        FeatureBankError,
        match="must be unique",
    ):
        generate_fake_bank(
            manifest=manifest,
            dataset_root=dataset_root,
            artifact_dir=tmp_path / "rejected",
        )


def test_drop_last_is_rejected_for_feature_bank(
    tmp_path: Path,
) -> None:
    manifest, dataset_root = create_fake_manifest_dataset(
        tmp_path
    )

    with pytest.raises(
        FeatureBankError,
        match="drop_last=False",
    ):
        generate_training_feature_bank(
            manifest=manifest,
            dataset_root=dataset_root,
            artifact_dir=tmp_path / "rejected",
            dataloader_config=DataLoaderConfig(
                batch_size=3,
                drop_last=True,
            ),
            feature_extractor=FakeFeatureExtractor(),
            extractor_metadata=FAKE_EXTRACTOR_METADATA,
        )


def test_non_finite_features_are_rejected(
    tmp_path: Path,
) -> None:
    manifest, dataset_root = create_fake_manifest_dataset(
        tmp_path
    )

    with pytest.raises(
        FeatureBankError,
        match="finite",
    ):
        generate_training_feature_bank(
            manifest=manifest,
            dataset_root=dataset_root,
            artifact_dir=tmp_path / "rejected",
            dataloader_config=DataLoaderConfig(batch_size=2),
            feature_extractor=NonFiniteFeatureExtractor(),
            extractor_metadata=FAKE_EXTRACTOR_METADATA,
        )

    assert not (tmp_path / "rejected").exists()


def test_inconsistent_feature_dimension_is_rejected(
    tmp_path: Path,
) -> None:
    manifest, dataset_root = create_fake_manifest_dataset(
        tmp_path
    )

    with pytest.raises(
        FeatureBankError,
        match="shape",
    ):
        generate_training_feature_bank(
            manifest=manifest,
            dataset_root=dataset_root,
            artifact_dir=tmp_path / "rejected",
            dataloader_config=DataLoaderConfig(batch_size=2),
            feature_extractor=WrongDimensionFeatureExtractor(),
            extractor_metadata=FAKE_EXTRACTOR_METADATA,
        )

    assert not (tmp_path / "rejected").exists()


def test_json_manifest_reader_restores_existing_types(
    tmp_path: Path,
) -> None:
    manifest, _ = create_fake_manifest_dataset(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(asdict(manifest)),
        encoding="utf-8",
    )

    loaded = read_json_manifest(manifest_path)

    assert loaded == manifest
