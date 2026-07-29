import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from torch import Tensor

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
)
from ml.data.build_manifest import (
    DatasetManifest,
    ManifestRecord,
)
from ml.data.torch_dataloader import DataLoaderConfig
from ml.generate_feature_bank import (
    FeatureExtractorMetadata,
    generate_training_feature_bank,
)
from ml.score_anomalies import (
    SCORE_ARTIFACT_CODE_VERSION,
    SCORE_ARTIFACT_SCHEMA_VERSION,
    generate_score_artifact,
)


class FakeFeatureExtractor:
    feature_dim = 3

    def extract(self, images: Tensor) -> Tensor:
        return images.mean(dim=(2, 3))


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
    15,
    0,
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


def create_mask(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(
        mode="L",
        size=(12, 10),
        color=255,
    ).save(path, format="PNG")


def create_record(
    *,
    sample_id: str,
    image_path: str,
    split: str,
    is_anomaly: bool = False,
    mask_path: str | None = None,
) -> ManifestRecord:
    return ManifestRecord(
        sample_id=sample_id,
        image_path=image_path,
        split=split,
        label=int(is_anomaly),
        class_name="crack" if is_anomaly else "good",
        is_anomaly=is_anomaly,
        mask_path=mask_path,
        width=12,
        height=10,
        image_format="PNG",
        mode="RGB",
    )


def create_scoring_fixture(
    tmp_path: Path,
) -> tuple[
    DatasetManifest,
    Path,
    ImagePreprocessingService,
]:
    dataset_root = tmp_path / "tile"
    records = [
        create_record(
            sample_id="train-001",
            image_path="train/good/001.png",
            split="train",
        ),
        create_record(
            sample_id="train-002",
            image_path="train/good/002.png",
            split="train",
        ),
        create_record(
            sample_id="validation-001",
            image_path="train/good/003.png",
            split="validation",
        ),
        create_record(
            sample_id="test-good-001",
            image_path="test/good/001.png",
            split="test",
        ),
        create_record(
            sample_id="test-crack-001",
            image_path="test/crack/001.png",
            split="test",
            is_anomaly=True,
            mask_path=(
                "ground_truth/crack/001_mask.png"
            ),
        ),
    ]

    create_rgb_image(
        dataset_root / records[0].image_path,
        (0, 0, 0),
    )
    create_rgb_image(
        dataset_root / records[1].image_path,
        (20, 0, 0),
    )
    create_rgb_image(
        dataset_root / records[2].image_path,
        (10, 0, 0),
    )
    create_rgb_image(
        dataset_root / records[3].image_path,
        (10, 0, 0),
    )
    create_rgb_image(
        dataset_root / records[4].image_path,
        (255, 255, 255),
    )
    create_mask(
        dataset_root / records[4].mask_path
    )

    manifest = DatasetManifest(
        dataset_name="fake",
        category="tile",
        dataset_version="fake-score-dataset-v1",
        random_seed=42,
        validation_ratio=0.2,
        records=records,
    )
    preprocessing_service = ImagePreprocessingService(
        target_width=8,
        target_height=6,
    )
    return (
        manifest,
        dataset_root,
        preprocessing_service,
    )


def test_score_artifact_preserves_metadata_order_and_lineage(
    tmp_path: Path,
) -> None:
    (
        manifest,
        dataset_root,
        preprocessing_service,
    ) = create_scoring_fixture(tmp_path)
    feature_bank_dir = tmp_path / "feature-bank"
    loader_config = DataLoaderConfig(
        batch_size=2,
        random_seed=42,
    )

    generate_training_feature_bank(
        manifest=manifest,
        dataset_root=dataset_root,
        artifact_dir=feature_bank_dir,
        dataloader_config=loader_config,
        feature_extractor=FakeFeatureExtractor(),
        extractor_metadata=FAKE_EXTRACTOR_METADATA,
        preprocessing_service=preprocessing_service,
        created_at=FIXED_CREATED_AT,
    )

    artifact = generate_score_artifact(
        manifest=manifest,
        dataset_root=dataset_root,
        feature_bank_dir=feature_bank_dir,
        artifact_dir=tmp_path / "scores",
        dataloader_config=loader_config,
        feature_extractor=FakeFeatureExtractor(),
        extractor_metadata=FAKE_EXTRACTOR_METADATA,
        k=1,
        preprocessing_service=preprocessing_service,
        created_at=FIXED_CREATED_AT,
    )

    assert [
        record.sample_id
        for record in artifact.records
    ] == [
        "validation-001",
        "test-good-001",
        "test-crack-001",
    ]
    assert [
        record.split
        for record in artifact.records
    ] == [
        "validation",
        "test",
        "test",
    ]
    assert [
        record.label
        for record in artifact.records
    ] == [0, 0, 1]
    assert [
        record.defect_type
        for record in artifact.records
    ] == [
        "good",
        "good",
        "crack",
    ]
    assert [
        record.has_mask
        for record in artifact.records
    ] == [
        False,
        False,
        True,
    ]
    assert [
        record.source_path
        for record in artifact.records
    ] == [
        "train/good/003.png",
        "test/good/001.png",
        "test/crack/001.png",
    ]
    assert (
        artifact.records[0].anomaly_score
        == artifact.records[1].anomaly_score
    )
    assert (
        artifact.records[2].anomaly_score
        > artifact.records[1].anomaly_score
    )

    payload = json.loads(
        artifact.scores_path.read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == (
        SCORE_ARTIFACT_SCHEMA_VERSION
    )
    assert payload["code_version"] == (
        SCORE_ARTIFACT_CODE_VERSION
    )
    assert payload["created_at"] == (
        "2026-07-29T15:00:00Z"
    )
    assert payload["dataset"]["version"] == (
        manifest.dataset_version
    )
    assert payload["feature_bank"]["sample_count"] == 2
    assert payload["feature_bank"]["split"] == "train"
    assert payload["feature_extractor"]["name"] == (
        "test.fake_mean"
    )
    assert payload["scorer"] == {
        "distance": "euclidean",
        "aggregation": "mean_k_nearest",
        "k": 1,
        "higher_is_more_anomalous": True,
    }
    assert payload["splits"] == [
        "validation",
        "test",
    ]
    assert payload["score_count"] == 3
    assert "threshold" not in payload
    assert "metrics" not in payload
    assert not list(artifact.artifact_dir.glob(".*.tmp"))
