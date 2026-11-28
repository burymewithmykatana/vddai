"""Bounded aggregate monitoring of the frozen image and inference signals."""

import math
import time
from bisect import bisect_left
from collections import deque
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Literal

import numpy as np
from prometheus_client.core import GaugeMetricFamily
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts.inference import AnomalyInferenceResult, PredictionLabel
from app.services.image_preprocessing_service import PreprocessedImage

FORMATS = ("jpeg", "png", "webp", "other")
DIMENSION_BOUNDS = (128, 256, 512, 1024, 2048, 4096, 8192)
SCORE_BOUNDS = (0.25, 0.5, 1, 2, 4, 8, 16, 32, 64, 128)
WINDOW_MINUTES = 60
MIN_OBSERVATIONS = 30
MAX_REFERENCE_BYTES = 8192
WARNING_SIGNALS = (
    "pixel_mean",
    "pixel_contrast",
    "format_mix",
    "anomaly_rate",
    "score_p95",
)


def monitored_format(name: str | None) -> str:
    value = name.lower() if name else ""
    return value if value in FORMATS else "other"


class QualityReference(BaseModel):
    """Aggregate baseline for one exact package and manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["vddai.quality_reference.v1"]
    source: Literal["normal_validation", "synthetic_fixture"]
    package_id: str = Field(
        min_length=8, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]+$"
    )
    manifest_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    preprocessing_version: Literal["vddai.preprocessing.rgb_chw_bilinear.v1"]
    count: int = Field(ge=MIN_OBSERVATIONS)
    format_counts: dict[Literal["jpeg", "png", "webp", "other"], int]
    pixel_mean: float = Field(ge=0, le=1, allow_inf_nan=False)
    pixel_contrast: float = Field(ge=0, le=0.5, allow_inf_nan=False)
    anomaly_count: int = Field(ge=0)
    score_p95: float = Field(ge=0, le=1e100, allow_inf_nan=False)

    @model_validator(mode="after")
    def check_counts(self):
        if (
            set(self.format_counts) != set(FORMATS)
            or any(value < 0 for value in self.format_counts.values())
            or sum(self.format_counts.values()) != self.count
            or self.anomaly_count > self.count
        ):
            raise ValueError("Invalid quality reference counts.")
        return self


def read_quality_reference(
    path: Path | None, *, allow_synthetic: bool = False
) -> QualityReference | None:
    if path is None or not path.is_file():
        return None
    try:
        with path.open("rb") as source:
            contents = source.read(MAX_REFERENCE_BYTES + 1)
        if len(contents) > MAX_REFERENCE_BYTES:
            return None
        reference = QualityReference.model_validate_json(contents)
    except (OSError, ValueError):
        return None
    if reference.source == "synthetic_fixture" and not allow_synthetic:
        return None
    return reference


@dataclass(frozen=True)
class ImageQuality:
    format: str
    width: int
    height: int
    mean: float
    contrast: float


def image_quality(image: PreprocessedImage) -> ImageQuality:
    return ImageQuality(
        format=monitored_format(image.original_format),
        width=image.original_width,
        height=image.original_height,
        mean=float(np.mean(image.array, dtype=np.float64)),
        contrast=float(np.std(image.array, dtype=np.float64)),
    )


quality_observer: ContextVar[
    Callable[[PreprocessedImage, AnomalyInferenceResult], None] | None
] = ContextVar("quality_observer", default=None)


def _bins(bounds: tuple[int | float, ...]) -> list[int]:
    return [0] * (len(bounds) + 1)


@dataclass
class _Minute:
    minute: int
    count: int = 0
    formats: list[int] = field(default_factory=lambda: [0] * len(FORMATS))
    widths: list[int] = field(default_factory=lambda: _bins(DIMENSION_BOUNDS))
    heights: list[int] = field(default_factory=lambda: _bins(DIMENSION_BOUNDS))
    scores: list[int] = field(default_factory=lambda: _bins(SCORE_BOUNDS))
    mean_sum: float = 0
    contrast_sum: float = 0
    anomalies: int = 0
    over_score_limit: int = 0

    def add(
        self, image: ImageQuality, result: AnomalyInferenceResult, score_limit: float
    ) -> None:
        self.count += 1
        self.formats[FORMATS.index(image.format)] += 1
        self.widths[bisect_left(DIMENSION_BOUNDS, image.width)] += 1
        self.heights[bisect_left(DIMENSION_BOUNDS, image.height)] += 1
        self.scores[bisect_left(SCORE_BOUNDS, result.anomaly_score)] += 1
        self.mean_sum += image.mean
        self.contrast_sum += image.contrast
        self.anomalies += result.predicted_label == PredictionLabel.ANOMALOUS
        self.over_score_limit += result.anomaly_score > score_limit


class QualityWindow:
    """Keep one model identity and at most 60 buckets of aggregate counts."""

    def __init__(self, reference: QualityReference | None) -> None:
        self._reference = reference
        self._lock = Lock()
        self._minutes: deque[_Minute] = deque()
        self._identity: tuple[str, str, str] | None = None
        self._mixed_until = 0

    def _expire(self, minute: int) -> None:
        while self._minutes and self._minutes[0].minute <= minute - WINDOW_MINUTES:
            self._minutes.popleft()

    def observe(self, image: PreprocessedImage, result: AnomalyInferenceResult) -> None:
        measured = image_quality(image)
        lineage = result.model_lineage
        identity = (
            result.model_version,
            lineage.manifest_fingerprint,
            lineage.preprocessing_schema_version,
        )
        ref = self._reference
        score_limit = ref.score_p95 * 1.5 if ref else math.inf
        with self._lock:
            minute = int(time.monotonic() // 60)
            self._expire(minute)
            if self._identity != identity:
                if self._minutes:
                    self._mixed_until = self._minutes[-1].minute + WINDOW_MINUTES
                    self._minutes.clear()
                self._identity = identity
            if not self._minutes or self._minutes[-1].minute != minute:
                self._minutes.append(_Minute(minute))
            self._minutes[-1].add(measured, result, score_limit)

    def collect(self) -> Iterator[GaugeMetricFamily]:
        with self._lock:
            minute = int(time.monotonic() // 60)
            self._expire(minute)
            count = sum(bucket.count for bucket in self._minutes)
            identity = self._identity
            ref = self._reference
            ready = (
                ref is not None
                and (
                    ref.package_id,
                    ref.manifest_fingerprint,
                    ref.preprocessing_version,
                )
                == identity
                and minute >= self._mixed_until
                and count >= MIN_OBSERVATIONS
            )
            formats = tuple(
                sum(bucket.formats[i] for bucket in self._minutes)
                for i in range(len(FORMATS))
            )
            mean = (
                sum(bucket.mean_sum for bucket in self._minutes) / count if count else 0
            )
            contrast = (
                sum(bucket.contrast_sum for bucket in self._minutes) / count
                if count
                else 0
            )
            anomalies = sum(bucket.anomalies for bucket in self._minutes)
            anomaly_rate = anomalies / count if count else 0
            over_score_limit = sum(bucket.over_score_limit for bucket in self._minutes)
            distributions = [
                (
                    name,
                    tuple(str(bound) for bound in bounds) + ("+Inf",),
                    tuple(
                        sum(getattr(bucket, series)[i] for bucket in self._minutes)
                        for i in range(len(bounds) + 1)
                    ),
                )
                for name, series, bounds in (
                    ("width", "widths", DIMENSION_BOUNDS),
                    ("height", "heights", DIMENSION_BOUNDS),
                    ("score", "scores", SCORE_BOUNDS),
                )
            ]
        yield GaugeMetricFamily(
            "vddai_quality_window_count",
            "Successful inference observations.",
            value=count,
        )
        yield GaugeMetricFamily(
            "vddai_quality_comparison_ready",
            "A matched quality comparison is available.",
            value=int(ready),
        )
        if ref:
            reference_info = GaugeMetricFamily(
                "vddai_quality_reference_count",
                "Reference sample count and source.",
                labels=["source"],
            )
            reference_info.add_metric([ref.source], ref.count)
            yield reference_info
        if identity and count:
            model = GaugeMetricFamily(
                "vddai_quality_package_info",
                "Observed immutable model identity.",
                labels=["package_id"],
            )
            model.add_metric([identity[0]], 1)
            yield model
            format_metric = GaugeMetricFamily(
                "vddai_quality_format_count",
                "Images in the window by decoded format.",
                labels=["format"],
            )
            for name, total in zip(FORMATS, formats, strict=True):
                format_metric.add_metric([name], total)
            yield format_metric
            bins = GaugeMetricFamily(
                "vddai_quality_window_bin_count",
                "Images in each noncumulative bin.",
                labels=["signal", "upper_bound"],
            )
            for series, bounds, totals in distributions:
                for bound, total in zip(bounds, totals, strict=True):
                    bins.add_metric([series, bound], total)
            yield bins
            yield GaugeMetricFamily(
                "vddai_quality_pixel_mean",
                "Mean of per-image normalized RGB means.",
                value=mean,
            )
            yield GaugeMetricFamily(
                "vddai_quality_pixel_contrast",
                "Mean of per-image normalized RGB standard deviations.",
                value=contrast,
            )
            yield GaugeMetricFamily(
                "vddai_quality_anomaly_rate",
                "Fraction of successful scores labeled anomalous.",
                value=anomaly_rate,
            )
        if ready and ref is not None:
            warning = GaugeMetricFamily(
                "vddai_quality_shift_warning",
                "Threshold crossed for the matched reference.",
                labels=["signal"],
            )
            thresholds = (
                abs(mean - ref.pixel_mean) >= 0.15,
                abs(contrast - ref.pixel_contrast) >= 0.1,
                any(
                    abs(total * ref.count - ref.format_counts[name] * count) * 5
                    >= ref.count * count
                    for name, total in zip(FORMATS, formats, strict=True)
                ),
                abs(anomalies * ref.count - ref.anomaly_count * count) * 5
                >= ref.count * count,
                count - over_score_limit < (95 * count + 99) // 100,
            )
            for signal, crossed in zip(WARNING_SIGNALS, thresholds, strict=True):
                warning.add_metric([signal], int(crossed))
            yield warning
