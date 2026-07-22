from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError

from app.services.image_preprocessing_service import (
    ImagePreprocessingService,
    image_preprocessing_service,
)
from ml.data.build_manifest import (
    DatasetManifest,
    ManifestRecord,
)
from ml.data.process_manifest import (
    ManifestProcessingError,
    process_manifest_record,
    resolve_manifest_path,
)


FloatImageArray = NDArray[np.float32]
MaskArray = NDArray[np.uint8]
LabelArray = NDArray[np.int64]
BooleanArray = NDArray[np.bool_]


class DatasetLoadingError(RuntimeError):
    """Raised when a manifest dataset cannot produce a valid sample."""


@dataclass(frozen=True)
class DatasetSample:
    sample_id: str
    split: str
    label: int
    class_name: str
    is_anomaly: bool
    source_path: str
    mask_path: str | None
    image: FloatImageArray
    mask: MaskArray
    has_mask: bool


@dataclass(frozen=True)
class DatasetBatch:
    sample_ids: tuple[str, ...]
    source_paths: tuple[str, ...]
    class_names: tuple[str, ...]
    images: FloatImageArray
    labels: LabelArray
    masks: MaskArray
    has_masks: BooleanArray


def preprocess_mask(
    mask_path: Path,
    target_width: int,
    target_height: int,
) -> MaskArray:
    if target_width <= 0 or target_height <= 0:
        raise ValueError(
            "Target mask dimensions must be positive."
        )

    try:
        with Image.open(mask_path) as image:
            grayscale_mask = image.convert("L")

            resized_mask = grayscale_mask.resize(
                (target_width, target_height),
                resample=Image.Resampling.NEAREST,
            )

            mask_array = np.asarray(
                resized_mask,
                dtype=np.uint8,
            )

    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise DatasetLoadingError(
            "Ground-truth mask could not be decoded: "
            f"{mask_path.as_posix()}"
        ) from exc

    # MVTec masks are binary, but threshold explicitly so that
    # the resulting contract is always {0, 1}.
    mask_array = (
        mask_array > 0
    ).astype(
        np.uint8,
        copy=False,
    )

    mask_array = np.expand_dims(
        mask_array,
        axis=0,
    )

    mask_array = np.ascontiguousarray(
        mask_array,
        dtype=np.uint8,
    )

    expected_shape = (
        1,
        target_height,
        target_width,
    )

    if mask_array.shape != expected_shape:
        raise DatasetLoadingError(
            "Unexpected mask shape. "
            f"Expected {expected_shape}, "
            f"received {mask_array.shape}."
        )

    unique_values = set(
        np.unique(mask_array).tolist()
    )

    if not unique_values.issubset({0, 1}):
        raise DatasetLoadingError(
            "Processed mask must be binary."
        )

    return mask_array


class ManifestDataset(Sequence[DatasetSample]):
    def __init__(
        self,
        manifest: DatasetManifest,
        dataset_root: Path,
        split: str,
        preprocessing_service: ImagePreprocessingService = (
            image_preprocessing_service
        ),
    ) -> None:
        allowed_splits = {
            "train",
            "validation",
            "test",
        }

        if split not in allowed_splits:
            raise ValueError(
                "split must be one of: "
                "train, validation, test"
            )

        self.dataset_root = dataset_root.resolve()
        self.split = split
        self.preprocessing_service = preprocessing_service

        self.records = tuple(
            record
            for record in manifest.records
            if record.split == split
        )

        if not self.records:
            raise DatasetLoadingError(
                f"Manifest contains no records for split: {split}"
            )

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(
        self,
        index: int,
    ) -> DatasetSample:
        record = self.records[index]

        return self._load_record(record)

    def __iter__(self) -> Iterator[DatasetSample]:
        for index in range(len(self)):
            yield self[index]

    def _load_record(
        self,
        record: ManifestRecord,
    ) -> DatasetSample:
        try:
            processed = process_manifest_record(
                record=record,
                dataset_root=self.dataset_root,
                preprocessing_service=(
                    self.preprocessing_service
                ),
            )
        except ManifestProcessingError as exc:
            raise DatasetLoadingError(
                "Dataset image could not be loaded: "
                f"{record.image_path}"
            ) from exc

        target_width = (
            self.preprocessing_service.target_width
        )
        target_height = (
            self.preprocessing_service.target_height
        )

        if record.is_anomaly:
            if record.mask_path is None:
                raise DatasetLoadingError(
                    "An anomalous sample must have a mask: "
                    f"{record.image_path}"
                )

            mask_file = resolve_manifest_path(
                dataset_root=self.dataset_root,
                relative_path=record.mask_path,
            )

            mask = preprocess_mask(
                mask_path=mask_file,
                target_width=target_width,
                target_height=target_height,
            )

            has_mask = True

        else:
            if record.mask_path is not None:
                raise DatasetLoadingError(
                    "A normal sample must not have a mask: "
                    f"{record.image_path}"
                )

            mask = np.zeros(
                (
                    1,
                    target_height,
                    target_width,
                ),
                dtype=np.uint8,
            )

            has_mask = False

        return DatasetSample(
            sample_id=processed.sample_id,
            split=processed.split,
            label=processed.label,
            class_name=processed.class_name,
            is_anomaly=processed.is_anomaly,
            source_path=processed.source_path,
            mask_path=record.mask_path,
            image=processed.model_input,
            mask=mask,
            has_mask=has_mask,
        )


def collate_samples(
    samples: Sequence[DatasetSample],
) -> DatasetBatch:
    if not samples:
        raise DatasetLoadingError(
            "Cannot create a batch from zero samples."
        )

    expected_image_shape = samples[0].image.shape
    expected_mask_shape = samples[0].mask.shape

    for sample in samples:
        if sample.image.shape != expected_image_shape:
            raise DatasetLoadingError(
                "All images in a batch must have "
                "the same shape."
            )

        if sample.mask.shape != expected_mask_shape:
            raise DatasetLoadingError(
                "All masks in a batch must have "
                "the same shape."
            )

    images = np.stack(
        [
            sample.image
            for sample in samples
        ],
        axis=0,
    ).astype(
        np.float32,
        copy=False,
    )

    labels = np.asarray(
        [
            sample.label
            for sample in samples
        ],
        dtype=np.int64,
    )

    masks = np.stack(
        [
            sample.mask
            for sample in samples
        ],
        axis=0,
    ).astype(
        np.uint8,
        copy=False,
    )

    has_masks = np.asarray(
        [
            sample.has_mask
            for sample in samples
        ],
        dtype=np.bool_,
    )

    images = np.ascontiguousarray(images)
    labels = np.ascontiguousarray(labels)
    masks = np.ascontiguousarray(masks)
    has_masks = np.ascontiguousarray(has_masks)

    if images.ndim != 4:
        raise DatasetLoadingError(
            "Batch images must use NCHW layout."
        )

    if masks.ndim != 4:
        raise DatasetLoadingError(
            "Batch masks must use NCHW layout."
        )

    return DatasetBatch(
        sample_ids=tuple(
            sample.sample_id
            for sample in samples
        ),
        source_paths=tuple(
            sample.source_path
            for sample in samples
        ),
        class_names=tuple(
            sample.class_name
            for sample in samples
        ),
        images=images,
        labels=labels,
        masks=masks,
        has_masks=has_masks,
    )