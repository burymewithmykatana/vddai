"""Score validation and test images against the normal feature bank.

Run with ``python -m ml.score_anomalies``. Labels are preserved in output
records for later evaluation but are never used to fit the scorer, choose k,
or select a threshold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
    image_preprocessing_service,
)
from ml.anomaly_scorer import (
    AnomalyScoringError,
    NearestNeighborAnomalyScorer,
)
from ml.data.build_manifest import (
    DEFAULT_RANDOM_SEED,
    DatasetManifest,
    read_json_manifest,
)
from ml.data.dataset import ManifestDataset
from ml.data.mvtec_contract import DATASET_ROOT, PROJECT_ROOT
from ml.data.torch_dataloader import (
    DataLoaderConfig,
    SplitName,
    create_split_dataloader,
)
from ml.data.torch_dataset import (
    TorchDatasetBatch,
    TorchManifestDataset,
)
from ml.feature_extractor import (
    FeatureExtractorConfig,
    ResNet18FeatureExtractor,
)
from ml.generate_feature_bank import (
    DEFAULT_ARTIFACT_DIR as DEFAULT_FEATURE_BANK_DIR,
    DEFAULT_EXTRACTOR_METADATA,
    DEFAULT_MANIFEST_PATH,
    FEATURE_BANK_SCHEMA_VERSION,
    FeatureExtractor,
    FeatureExtractorMetadata,
    calculate_manifest_fingerprint,
)

SCORE_ARTIFACT_SCHEMA_VERSION = "vddai.anomaly_scores.v1"
SCORE_ARTIFACT_CODE_VERSION = "vddai.anomaly_scores.generator.v1"
SCORES_FILENAME = "scores.json"
SCORED_SPLITS: tuple[SplitName, ...] = (
    "validation",
    "test",
)
DEFAULT_SCORE_ARTIFACT_DIR = (
    PROJECT_ROOT
    / "artifacts"
    / "anomaly_scores"
    / "mvtec_ad_tile_resnet18_knn"
)


class ScoreArtifactError(RuntimeError):
    """Raised when validation/test scores cannot be generated safely."""


@dataclass(frozen=True)
class ImageAnomalyScore:
    """One image-level score with its manifest metadata."""

    sample_id: str
    split: str
    label: int
    defect_type: str
    anomaly_score: float
    has_mask: bool
    source_path: str


@dataclass(frozen=True)
class ScoreArtifact:
    """Completed scoring artifact and its ordered records."""

    artifact_dir: Path
    scores_path: Path
    records: tuple[ImageAnomalyScore, ...]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as artifact_file:
        for chunk in iter(
            lambda: artifact_file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return f"sha256:{digest.hexdigest()}"


def _write_json_atomic(
    output_path: Path,
    payload: dict[str, object],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
        ) as temporary_file:
            json.dump(
                payload,
                temporary_file,
                indent=2,
                sort_keys=True,
            )
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _expected_extractor_payload(
    metadata: FeatureExtractorMetadata,
) -> dict[str, object]:
    return {
        "name": metadata.name,
        "pretrained_weights": metadata.pretrained_weights,
        "feature_layer": metadata.feature_layer,
        "feature_dimension": metadata.feature_dimension,
        "normalization": {
            "operation": "channelwise_standardization",
            "mean": list(metadata.normalization_mean),
            "std": list(metadata.normalization_std),
        },
    }


def _load_feature_bank_lineage(
    *,
    feature_bank_dir: Path,
    manifest: DatasetManifest,
    extractor_metadata: FeatureExtractorMetadata,
    preprocessing_service: ImagePreprocessingService,
) -> tuple[Path, dict[str, object]]:
    metadata_path = feature_bank_dir / "metadata.json"

    try:
        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ScoreArtifactError(
            "Feature-bank metadata could not be loaded."
        ) from exc

    if not isinstance(metadata, dict):
        raise ScoreArtifactError(
            "Feature-bank metadata must be a JSON object."
        )

    if metadata.get("schema_version") != (
        FEATURE_BANK_SCHEMA_VERSION
    ):
        raise ScoreArtifactError(
            "Unsupported feature-bank schema version."
        )

    if metadata.get("dataset_version") != (
        manifest.dataset_version
    ):
        raise ScoreArtifactError(
            "Feature-bank and manifest dataset versions must match."
        )

    if metadata.get("split") != "train":
        raise ScoreArtifactError(
            "Feature bank must contain training records only."
        )

    if metadata.get("feature_extractor") != (
        _expected_extractor_payload(extractor_metadata)
    ):
        raise ScoreArtifactError(
            "Feature-bank extractor lineage does not match."
        )

    if metadata.get("image_size") != {
        "height": preprocessing_service.target_height,
        "width": preprocessing_service.target_width,
    }:
        raise ScoreArtifactError(
            "Feature-bank image size does not match preprocessing."
        )

    if (
        not isinstance(metadata.get("code_version"), str)
        or not isinstance(metadata.get("sample_count"), int)
        or metadata["sample_count"] <= 0
    ):
        raise ScoreArtifactError(
            "Feature-bank lineage metadata is incomplete."
        )

    files = metadata.get("files")
    if not isinstance(files, dict):
        raise ScoreArtifactError(
            "Feature-bank file metadata is missing."
        )

    feature_file = files.get("features")
    if not isinstance(feature_file, dict):
        raise ScoreArtifactError(
            "Feature-bank archive metadata is missing."
        )

    relative_path = feature_file.get("path")
    expected_checksum = feature_file.get("sha256")

    if not isinstance(relative_path, str):
        raise ScoreArtifactError(
            "Feature-bank archive path is invalid."
        )

    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ScoreArtifactError(
            "Feature-bank archive path must be relative."
        )

    feature_bank_root = feature_bank_dir.resolve()
    features_path = (
        feature_bank_root / candidate
    ).resolve()

    try:
        features_path.relative_to(feature_bank_root)
    except ValueError as exc:
        raise ScoreArtifactError(
            "Feature-bank archive path escapes its artifact directory."
        ) from exc

    if not features_path.is_file():
        raise ScoreArtifactError(
            "Feature-bank archive does not exist."
        )

    if (
        not isinstance(expected_checksum, str)
        or _sha256_file(features_path) != expected_checksum
    ):
        raise ScoreArtifactError(
            "Feature-bank archive checksum does not match metadata."
        )

    return features_path, metadata


def _score_loader(
    *,
    loader: Iterable[TorchDatasetBatch],
    split: SplitName,
    feature_extractor: FeatureExtractor,
    scorer: NearestNeighborAnomalyScorer,
) -> tuple[ImageAnomalyScore, ...]:
    records: list[ImageAnomalyScore] = []

    for batch in loader:
        if set(batch.splits) != {split}:
            raise ScoreArtifactError(
                f"Loader emitted records outside the {split} split."
            )

        features = feature_extractor.extract(batch.images)
        scores = scorer.score(
            features.detach().to("cpu").numpy()
        )

        if scores.shape != (len(batch.sample_ids),):
            raise ScoreArtifactError(
                "Score count does not match the input batch."
            )

        for index, score in enumerate(scores):
            records.append(
                ImageAnomalyScore(
                    sample_id=batch.sample_ids[index],
                    split=batch.splits[index],
                    label=int(
                        batch.labels[index].item()
                    ),
                    defect_type=batch.class_names[index],
                    anomaly_score=float(score),
                    has_mask=bool(
                        batch.has_masks[index].item()
                    ),
                    source_path=batch.source_paths[index],
                )
            )

    return tuple(records)


def _validate_scored_records(
    *,
    manifest: DatasetManifest,
    split: SplitName,
    records: tuple[ImageAnomalyScore, ...],
) -> None:
    expected_ids = tuple(
        record.sample_id
        for record in manifest.records
        if record.split == split
    )
    actual_ids = tuple(
        record.sample_id
        for record in records
    )

    if actual_ids != expected_ids:
        raise ScoreArtifactError(
            f"{split} score records must preserve manifest order."
        )

    if len(set(actual_ids)) != len(actual_ids):
        raise ScoreArtifactError(
            f"{split} score sample IDs must be unique."
        )

    if not all(
        np.isfinite(record.anomaly_score)
        for record in records
    ):
        raise ScoreArtifactError(
            f"{split} scores must contain only finite values."
        )


def generate_score_artifact(
    *,
    manifest: DatasetManifest,
    dataset_root: Path,
    feature_bank_dir: Path,
    artifact_dir: Path,
    dataloader_config: DataLoaderConfig,
    feature_extractor: FeatureExtractor,
    extractor_metadata: FeatureExtractorMetadata,
    k: int = 1,
    preprocessing_service: ImagePreprocessingService = (
        image_preprocessing_service
    ),
    created_at: datetime | None = None,
) -> ScoreArtifact:
    """Score validation and test splits and write their lineage artifact."""
    if dataloader_config.drop_last:
        raise ScoreArtifactError(
            "Score generation requires drop_last=False."
        )

    if feature_extractor.feature_dim != (
        extractor_metadata.feature_dimension
    ):
        raise ScoreArtifactError(
            "Extractor dimension does not match its lineage metadata."
        )

    features_path, feature_bank_metadata = (
        _load_feature_bank_lineage(
            feature_bank_dir=feature_bank_dir,
            manifest=manifest,
            extractor_metadata=extractor_metadata,
            preprocessing_service=preprocessing_service,
        )
    )

    try:
        scorer = NearestNeighborAnomalyScorer(
            k=k
        ).load(features_path)
    except AnomalyScoringError as exc:
        raise ScoreArtifactError(
            "Feature bank cannot initialize the anomaly scorer."
        ) from exc

    if scorer.feature_dimension != (
        extractor_metadata.feature_dimension
    ):
        raise ScoreArtifactError(
            "Feature-bank dimension does not match extractor lineage."
        )

    if scorer.bank_size != feature_bank_metadata[
        "sample_count"
    ]:
        raise ScoreArtifactError(
            "Feature-bank row count does not match its metadata."
        )

    split_records: dict[
        SplitName,
        tuple[ImageAnomalyScore, ...],
    ] = {}

    for split in SCORED_SPLITS:
        manifest_dataset = ManifestDataset(
            manifest=manifest,
            dataset_root=dataset_root,
            split=split,
            preprocessing_service=preprocessing_service,
        )
        torch_dataset = TorchManifestDataset(
            manifest_dataset
        )
        loader = create_split_dataloader(
            dataset=torch_dataset,
            split=split,
            config=dataloader_config,
        )
        records = _score_loader(
            loader=loader,
            split=split,
            feature_extractor=feature_extractor,
            scorer=scorer,
        )
        _validate_scored_records(
            manifest=manifest,
            split=split,
            records=records,
        )
        split_records[split] = records

    ordered_records = tuple(
        record
        for split in SCORED_SPLITS
        for record in split_records[split]
    )

    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ScoreArtifactError(
            "Creation timestamp must include timezone information."
        )
    created_at_utc = (
        timestamp.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    artifact_dir = artifact_dir.resolve()
    scores_path = artifact_dir / SCORES_FILENAME
    score_payload: dict[str, object] = {
        "schema_version": SCORE_ARTIFACT_SCHEMA_VERSION,
        "code_version": SCORE_ARTIFACT_CODE_VERSION,
        "created_at": created_at_utc,
        "dataset": {
            "name": manifest.dataset_name,
            "category": manifest.category,
            "version": manifest.dataset_version,
            "manifest_fingerprint": (
                calculate_manifest_fingerprint(manifest)
            ),
        },
        "feature_bank": {
            "schema_version": feature_bank_metadata[
                "schema_version"
            ],
            "code_version": feature_bank_metadata[
                "code_version"
            ],
            "dataset_version": feature_bank_metadata[
                "dataset_version"
            ],
            "sample_count": feature_bank_metadata[
                "sample_count"
            ],
            "split": feature_bank_metadata["split"],
            "features_sha256": feature_bank_metadata[
                "files"
            ]["features"]["sha256"],
        },
        "feature_extractor": feature_bank_metadata[
            "feature_extractor"
        ],
        "scorer": {
            "distance": "euclidean",
            "aggregation": "mean_k_nearest",
            "k": k,
            "higher_is_more_anomalous": True,
        },
        "random_seed": dataloader_config.random_seed,
        "splits": list(SCORED_SPLITS),
        "score_count": len(ordered_records),
        "records": [
            asdict(record)
            for record in ordered_records
        ],
    }
    _write_json_atomic(scores_path, score_payload)

    return ScoreArtifact(
        artifact_dir=artifact_dir,
        scores_path=scores_path,
        records=ordered_records,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score validation and test images against the normal "
            "feature bank."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DATASET_ROOT,
    )
    parser.add_argument(
        "--feature-bank-dir",
        type=Path,
        default=DEFAULT_FEATURE_BANK_DIR,
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=DEFAULT_SCORE_ARTIFACT_DIR,
    )
    parser.add_argument(
        "--k",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--pin-memory",
        action="store_true",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="PyTorch device, for example cpu or cuda.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = read_json_manifest(args.manifest)
    feature_extractor = ResNet18FeatureExtractor(
        config=FeatureExtractorConfig(
            device=args.device,
        )
    )
    artifact = generate_score_artifact(
        manifest=manifest,
        dataset_root=args.dataset_root,
        feature_bank_dir=args.feature_bank_dir,
        artifact_dir=args.artifact_dir,
        dataloader_config=DataLoaderConfig(
            batch_size=args.batch_size,
            random_seed=args.random_seed,
            num_workers=args.num_workers,
            pin_memory=args.pin_memory,
            drop_last=False,
        ),
        feature_extractor=feature_extractor,
        extractor_metadata=DEFAULT_EXTRACTOR_METADATA,
        k=args.k,
    )

    split_counts = {
        split: sum(
            record.split == split
            for record in artifact.records
        )
        for split in SCORED_SPLITS
    }
    print("Image-level anomaly scores generated")
    print(f"Records: {len(artifact.records)}")
    print(f"Split counts: {split_counts}")
    print(f"Scores: {artifact.scores_path}")


if __name__ == "__main__":
    main()
