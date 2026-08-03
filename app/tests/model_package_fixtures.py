"""Tiny deterministic model-package fixtures for loader and inference tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import Tensor

from app.services.model_package_loader import EXPECTED_EXTRACTOR
from ml.evaluate_baseline import (
    EVALUATION_CODE_VERSION,
    EVALUATION_SCHEMA_VERSION,
)
from ml.generate_feature_bank import (
    FEATURE_BANK_CODE_VERSION,
    FEATURE_BANK_SCHEMA_VERSION,
)
from ml.select_threshold import (
    THRESHOLD_ARTIFACT_CODE_VERSION,
    THRESHOLD_ARTIFACT_SCHEMA_VERSION,
)
from ml.threshold_selector import THRESHOLD_POLICY_NAME


class ConstantFeatureExtractor:
    feature_dim = 512

    def __init__(self, value: float = 2.0) -> None:
        self.value = value
        self.received_images: Tensor | None = None

    def extract(self, images: Tensor) -> Tensor:
        self.received_images = images.clone()
        features = torch.zeros((images.shape[0], self.feature_dim))
        features[:, 0] = self.value
        return features


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


@dataclass(frozen=True)
class PackageFixture:
    root: Path
    run_dir: Path
    manifest_path: Path
    threshold_path: Path
    feature_bank_dir: Path
    features_path: Path

    def refresh_threshold_checksum(self) -> None:
        manifest = read_json(self.manifest_path)
        artifacts = manifest["artifacts"]
        assert isinstance(artifacts, dict)
        threshold_file = artifacts["threshold.json"]
        assert isinstance(threshold_file, dict)
        threshold_file["sha256"] = sha256_file(self.threshold_path)
        write_json(self.manifest_path, manifest)


def write_package_fixture(
    root: Path,
    *,
    threshold: float = 2.0,
    scorer_k: int = 1,
) -> PackageFixture:
    feature_bank_dir = root / "feature-bank"
    feature_bank_dir.mkdir(parents=True)
    features_path = feature_bank_dir / "features.npz"
    np.savez_compressed(
        features_path,
        features=np.zeros((2, 512), dtype=np.float32),
        sample_ids=np.asarray(["normal-1", "normal-2"], dtype=np.str_),
        source_paths=np.asarray(["a.png", "b.png"], dtype=np.str_),
        splits=np.asarray(["train", "train"], dtype=np.str_),
        dataset_versions=np.asarray(["dataset-v1", "dataset-v1"]),
    )
    feature_checksum = sha256_file(features_path)
    dataset = {
        "name": "MVTec AD",
        "category": "tile",
        "version": "dataset-v1",
        "manifest_fingerprint": f"sha256:{'a' * 64}",
    }
    feature_bank_lineage = {
        "schema_version": FEATURE_BANK_SCHEMA_VERSION,
        "code_version": FEATURE_BANK_CODE_VERSION,
        "dataset_version": "dataset-v1",
        "sample_count": 2,
        "split": "train",
        "features_sha256": feature_checksum,
    }
    scorer = {
        "distance": "euclidean",
        "aggregation": "mean_k_nearest",
        "k": scorer_k,
        "higher_is_more_anomalous": True,
    }
    feature_bank_metadata = {
        "schema_version": FEATURE_BANK_SCHEMA_VERSION,
        "code_version": FEATURE_BANK_CODE_VERSION,
        "created_at": "2026-08-03T00:00:00Z",
        "split": "train",
        "sample_count": 2,
        "dataset_version": "dataset-v1",
        "manifest_fingerprint": f"sha256:{'a' * 64}",
        "random_seed": 42,
        "image_size": {"height": 224, "width": 224},
        "feature_extractor": EXPECTED_EXTRACTOR,
        "files": {
            "features": {
                "path": "features.npz",
                "sha256": feature_checksum,
            }
        },
    }
    write_json(feature_bank_dir / "metadata.json", feature_bank_metadata)

    run_dir = root / "promoted-run"
    run_dir.mkdir()
    threshold_path = run_dir / "threshold.json"
    threshold_artifact = {
        "schema_version": THRESHOLD_ARTIFACT_SCHEMA_VERSION,
        "code_version": THRESHOLD_ARTIFACT_CODE_VERSION,
        "created_at": "2026-08-03T00:00:00Z",
        "calibration": {
            "split": "validation",
            "mode": "normal_only",
            "uses_test_scores": False,
            "uses_test_labels": False,
            "quantile_method": "linear",
        },
        "prediction_semantics": {
            "anomalous": "score > threshold",
            "normal": "score <= threshold",
        },
        "threshold_selection": {
            "threshold": threshold,
            "quantile": 0.95,
            "threshold_policy": THRESHOLD_POLICY_NAME,
        },
        "dataset": dataset,
        "feature_bank": feature_bank_lineage,
        "feature_extractor": EXPECTED_EXTRACTOR,
        "scorer": scorer,
    }
    write_json(threshold_path, threshold_artifact)

    manifest_path = run_dir / "run_manifest.json"
    manifest = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "code_version": EVALUATION_CODE_VERSION,
        "created_at": "2026-08-03T00:00:00Z",
        "run_name": "promoted-run",
        "run_type": "image_level_anomaly_evaluation",
        "protocol": {
            "evaluation_split": "test",
            "feature_bank_fit_split": "train",
            "higher_scores_mean": "more_anomalous",
            "prediction_rule": "score > threshold",
            "retune_after_test_evaluation": False,
            "threshold_selection_split": "validation",
        },
        "effective_configuration": {
            "threshold_quantile": 0.95,
            "random_seed": 42,
            "scored_splits": ["validation", "test"],
            "scorer": scorer,
        },
        "threshold_policy": {
            "name": THRESHOLD_POLICY_NAME,
            "quantile": 0.95,
            "threshold": threshold,
            "calibration_split": "validation",
            "calibration_mode": "normal_only",
        },
        "lineage": {
            "dataset": dataset,
            "feature_bank": feature_bank_lineage,
            "feature_extractor": EXPECTED_EXTRACTOR,
            "source_scores": {
                "schema_version": "vddai.anomaly_scores.v1",
                "code_version": "vddai.anomaly_scores.generator.v1",
                "sha256": f"sha256:{'d' * 64}",
            },
        },
        "artifacts": {
            "threshold.json": {
                "path": "threshold.json",
                "sha256": sha256_file(threshold_path),
            }
        },
    }
    write_json(manifest_path, manifest)
    return PackageFixture(
        root=root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        threshold_path=threshold_path,
        feature_bank_dir=feature_bank_dir,
        features_path=features_path,
    )
