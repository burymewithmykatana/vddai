"""Generate the Week 4 normal-image feature bank.

Run with ``python -m ml.generate_feature_bank``. The command loads the
validated training manifest through ``ManifestDataset`` and its PyTorch
adapter, then extracts one frozen ResNet-18 representation per normal sample.
It does not perform threshold selection or anomaly scoring.
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
from typing import Protocol

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
    image_preprocessing_service,
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
    create_split_dataloader,
)
from ml.data.torch_dataset import (
    TorchDatasetBatch,
    TorchManifestDataset,
)
from ml.feature_extractor import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    RESNET18_EXTRACTOR_NAME,
    RESNET18_FEATURE_DIM,
    RESNET18_FEATURE_LAYER,
    RESNET18_WEIGHTS_IDENTIFIER,
    FeatureExtractorConfig,
    ResNet18FeatureExtractor,
)

FEATURE_BANK_SCHEMA_VERSION = "vddai.feature_bank.v1"
FEATURE_BANK_CODE_VERSION = "vddai.feature_bank.generator.v1"
FEATURES_FILENAME = "features.npz"
METADATA_FILENAME = "metadata.json"

DEFAULT_MANIFEST_PATH = (
    PROJECT_ROOT
    / "data"
    / "metadata"
    / "mvtec_ad_tile_manifest.generated.json"
)
DEFAULT_ARTIFACT_DIR = (
    PROJECT_ROOT
    / "artifacts"
    / "feature_banks"
    / "mvtec_ad_tile_train_resnet18"
)

FloatFeatureArray = NDArray[np.float32]


class FeatureBankError(RuntimeError):
    """Raised when a valid normal feature bank cannot be generated."""


class FeatureExtractor(Protocol):
    """Minimal interface required by feature-bank generation."""

    feature_dim: int

    def extract(self, images: Tensor) -> Tensor:
        """Return one feature vector per image."""


@dataclass(frozen=True)
class FeatureExtractorMetadata:
    """Serializable identity and normalization contract for an extractor."""

    name: str
    pretrained_weights: str
    feature_layer: str
    feature_dimension: int
    normalization_mean: tuple[float, float, float]
    normalization_std: tuple[float, float, float]


@dataclass(frozen=True)
class FeatureBankArtifact:
    """Paths and ordered sample IDs for a completed feature bank."""

    artifact_dir: Path
    features_path: Path
    metadata_path: Path
    sample_ids: tuple[str, ...]


DEFAULT_EXTRACTOR_METADATA = FeatureExtractorMetadata(
    name=RESNET18_EXTRACTOR_NAME,
    pretrained_weights=RESNET18_WEIGHTS_IDENTIFIER,
    feature_layer=RESNET18_FEATURE_LAYER,
    feature_dimension=RESNET18_FEATURE_DIM,
    normalization_mean=IMAGENET_MEAN,
    normalization_std=IMAGENET_STD,
)


def calculate_manifest_fingerprint(
    manifest: DatasetManifest,
) -> str:
    """Return a SHA-256 fingerprint over the complete manifest payload."""
    canonical_manifest = json.dumps(
        asdict(manifest),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(
        canonical_manifest.encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as artifact_file:
        for chunk in iter(
            lambda: artifact_file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return f"sha256:{digest.hexdigest()}"


def _write_npz_atomic(
    output_path: Path,
    *,
    features: FloatFeatureArray,
    sample_ids: NDArray[np.str_],
    source_paths: NDArray[np.str_],
    splits: NDArray[np.str_],
    dataset_versions: NDArray[np.str_],
) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            np.savez_compressed(
                temporary_file,
                features=features,
                sample_ids=sample_ids,
                source_paths=source_paths,
                splits=splits,
                dataset_versions=dataset_versions,
            )
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        checksum = _sha256_file(temporary_path)
        os.replace(temporary_path, output_path)
        return checksum
    finally:
        temporary_path.unlink(missing_ok=True)


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


def _validate_training_records(
    manifest: DatasetManifest,
) -> tuple[str, ...]:
    train_records = tuple(
        record
        for record in manifest.records
        if record.split == "train"
    )

    if not train_records:
        raise FeatureBankError(
            "Manifest contains no training samples."
        )

    if any(
        record.label != 0
        or record.is_anomaly
        or record.mask_path is not None
        for record in train_records
    ):
        raise FeatureBankError(
            "Feature-bank training records must all be normal."
        )

    sample_ids = tuple(
        record.sample_id
        for record in train_records
    )

    if len(set(sample_ids)) != len(sample_ids):
        raise FeatureBankError(
            "Training sample IDs must be unique."
        )

    return sample_ids


def _collect_features(
    loader: Iterable[TorchDatasetBatch],
    feature_extractor: FeatureExtractor,
    feature_dimension: int,
) -> tuple[
    FloatFeatureArray,
    tuple[str, ...],
    tuple[str, ...],
]:
    feature_batches: list[FloatFeatureArray] = []
    sample_ids: list[str] = []
    source_paths: list[str] = []

    for batch in loader:
        if set(batch.splits) != {"train"}:
            raise FeatureBankError(
                "Only training samples may enter the feature bank."
            )

        if torch.any(batch.labels != 0).item():
            raise FeatureBankError(
                "Only normal samples may enter the feature bank."
            )

        if torch.any(batch.has_masks).item():
            raise FeatureBankError(
                "Normal feature-bank samples must not have masks."
            )

        features = feature_extractor.extract(batch.images)

        if features.dtype != torch.float32:
            raise FeatureBankError(
                "Extracted features must use torch.float32."
            )

        if features.ndim != 2:
            raise FeatureBankError(
                "Extracted features must have shape (N, D)."
            )

        if features.shape != (
            len(batch.sample_ids),
            feature_dimension,
        ):
            raise FeatureBankError(
                "Extracted feature shape does not match the batch contract."
            )

        if not torch.isfinite(features).all().item():
            raise FeatureBankError(
                "Extracted features must contain only finite values."
            )

        feature_batches.append(
            features.detach().to("cpu").numpy()
        )
        sample_ids.extend(batch.sample_ids)
        source_paths.extend(batch.source_paths)

    if not feature_batches:
        raise FeatureBankError(
            "DataLoader produced no feature batches."
        )

    feature_matrix = np.concatenate(
        feature_batches,
        axis=0,
    )
    return (
        feature_matrix,
        tuple(sample_ids),
        tuple(source_paths),
    )


def generate_training_feature_bank(
    *,
    manifest: DatasetManifest,
    dataset_root: Path,
    artifact_dir: Path,
    dataloader_config: DataLoaderConfig,
    feature_extractor: FeatureExtractor,
    extractor_metadata: FeatureExtractorMetadata,
    preprocessing_service: ImagePreprocessingService = (
        image_preprocessing_service
    ),
    created_at: datetime | None = None,
) -> FeatureBankArtifact:
    """Generate and atomically save a normal training feature bank."""
    if dataloader_config.drop_last:
        raise FeatureBankError(
            "Feature-bank generation requires drop_last=False."
        )

    expected_sample_ids = _validate_training_records(
        manifest
    )

    if (
        extractor_metadata.feature_dimension
        != feature_extractor.feature_dim
    ):
        raise FeatureBankError(
            "Extractor metadata dimension does not match the extractor."
        )

    manifest_dataset = ManifestDataset(
        manifest=manifest,
        dataset_root=dataset_root,
        split="train",
        preprocessing_service=preprocessing_service,
    )
    torch_dataset = TorchManifestDataset(manifest_dataset)
    loader = create_split_dataloader(
        dataset=torch_dataset,
        split="train",
        config=dataloader_config,
    )

    feature_matrix, sample_ids, source_paths = _collect_features(
        loader=loader,
        feature_extractor=feature_extractor,
        feature_dimension=extractor_metadata.feature_dimension,
    )

    expected_count = len(expected_sample_ids)
    if feature_matrix.shape != (
        expected_count,
        extractor_metadata.feature_dimension,
    ):
        raise FeatureBankError(
            "Feature row count or dimension does not match the manifest."
        )

    if len(sample_ids) != expected_count:
        raise FeatureBankError(
            "Feature row count does not match the training sample count."
        )

    if len(set(sample_ids)) != len(sample_ids):
        raise FeatureBankError(
            "Generated feature-bank sample IDs must be unique."
        )

    if set(sample_ids) != set(expected_sample_ids):
        raise FeatureBankError(
            "Generated feature-bank IDs do not match the training manifest."
        )

    if not np.isfinite(feature_matrix).all():
        raise FeatureBankError(
            "Feature matrix must contain only finite values."
        )

    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise FeatureBankError(
            "Creation timestamp must include timezone information."
        )
    created_at_utc = (
        timestamp.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    artifact_dir = artifact_dir.resolve()
    features_path = artifact_dir / FEATURES_FILENAME
    metadata_path = artifact_dir / METADATA_FILENAME

    sample_id_array = np.asarray(sample_ids, dtype=np.str_)
    source_path_array = np.asarray(source_paths, dtype=np.str_)
    split_array = np.asarray(
        ["train"] * expected_count,
        dtype=np.str_,
    )
    dataset_version_array = np.asarray(
        [manifest.dataset_version] * expected_count,
        dtype=np.str_,
    )

    features_checksum = _write_npz_atomic(
        features_path,
        features=feature_matrix,
        sample_ids=sample_id_array,
        source_paths=source_path_array,
        splits=split_array,
        dataset_versions=dataset_version_array,
    )

    metadata: dict[str, object] = {
        "schema_version": FEATURE_BANK_SCHEMA_VERSION,
        "code_version": FEATURE_BANK_CODE_VERSION,
        "created_at": created_at_utc,
        "split": "train",
        "sample_count": expected_count,
        "dataset_version": manifest.dataset_version,
        "manifest_fingerprint": calculate_manifest_fingerprint(
            manifest
        ),
        "random_seed": dataloader_config.random_seed,
        "image_size": {
            "height": preprocessing_service.target_height,
            "width": preprocessing_service.target_width,
        },
        "feature_extractor": {
            "name": extractor_metadata.name,
            "pretrained_weights": (
                extractor_metadata.pretrained_weights
            ),
            "feature_layer": extractor_metadata.feature_layer,
            "feature_dimension": (
                extractor_metadata.feature_dimension
            ),
            "normalization": {
                "operation": "channelwise_standardization",
                "mean": list(
                    extractor_metadata.normalization_mean
                ),
                "std": list(
                    extractor_metadata.normalization_std
                ),
            },
        },
        "files": {
            "features": {
                "path": FEATURES_FILENAME,
                "sha256": features_checksum,
            },
        },
    }
    _write_json_atomic(metadata_path, metadata)

    return FeatureBankArtifact(
        artifact_dir=artifact_dir,
        features_path=features_path,
        metadata_path=metadata_path,
        sample_ids=sample_ids,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a deterministic normal-training feature bank."
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
        "--artifact-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
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
    artifact = generate_training_feature_bank(
        manifest=manifest,
        dataset_root=args.dataset_root,
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
    )

    print("Normal feature bank generated")
    print(f"Samples: {len(artifact.sample_ids)}")
    print(f"Features: {artifact.features_path}")
    print(f"Metadata: {artifact.metadata_path}")


if __name__ == "__main__":
    main()
