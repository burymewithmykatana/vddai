from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from app.services.image_preprocessing_service import (
    ImagePreprocessingError,
    ImagePreprocessingService,
    image_preprocessing_service,
)
from ml.data.build_manifest import ManifestRecord


FloatImageArray = NDArray[np.float32]


class ManifestProcessingError(RuntimeError):
    """Raised when a manifest record cannot be processed safely."""


@dataclass(frozen=True)
class ProcessedSample:
    sample_id: str
    split: str
    label: int
    class_name: str
    is_anomaly: bool
    source_path: str
    model_input: FloatImageArray
    original_width: int
    original_height: int


def resolve_manifest_path(
    dataset_root: Path,
    relative_path: str,
) -> Path:
    root = dataset_root.resolve()
    candidate = Path(relative_path)

    if candidate.is_absolute():
        raise ManifestProcessingError(
            "Manifest paths must be relative."
        )

    resolved_path = (root / candidate).resolve()

    try:
        resolved_path.relative_to(root)
    except ValueError as exc:
        raise ManifestProcessingError(
            "Manifest path escapes the dataset root."
        ) from exc

    if not resolved_path.is_file():
        raise ManifestProcessingError(
            "Manifest image does not exist: "
            f"{relative_path}"
        )

    return resolved_path


def process_manifest_record(
    record: ManifestRecord,
    dataset_root: Path,
    preprocessing_service: ImagePreprocessingService = (
        image_preprocessing_service
    ),
) -> ProcessedSample:
    image_path = resolve_manifest_path(
        dataset_root=dataset_root,
        relative_path=record.image_path,
    )

    try:
        preprocessed = preprocessing_service.preprocess(
            image_path
        )
    except ImagePreprocessingError as exc:
        raise ManifestProcessingError(
            "Manifest image could not be preprocessed: "
            f"{record.image_path}"
        ) from exc

    model_input = preprocessed.array

    if model_input.dtype != np.float32:
        raise ManifestProcessingError(
            "Model input must have dtype float32."
        )

    if model_input.ndim != 3:
        raise ManifestProcessingError(
            "Model input must use CHW layout."
        )

    if model_input.shape[0] != 3:
        raise ManifestProcessingError(
            "Model input must contain three RGB channels."
        )

    if not model_input.flags.c_contiguous:
        raise ManifestProcessingError(
            "Model input must be C-contiguous."
        )

    if model_input.min() < 0.0:
        raise ManifestProcessingError(
            "Model input contains values below zero."
        )

    if model_input.max() > 1.0:
        raise ManifestProcessingError(
            "Model input contains values above one."
        )

    return ProcessedSample(
        sample_id=record.sample_id,
        split=record.split,
        label=record.label,
        class_name=record.class_name,
        is_anomaly=record.is_anomaly,
        source_path=record.image_path,
        model_input=model_input,
        original_width=preprocessed.original_width,
        original_height=preprocessed.original_height,
    )