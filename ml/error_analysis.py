"""Pure helpers for segmentation-aware image-level error analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np
from numpy.typing import ArrayLike

OutcomeName = Literal[
    "true_positive",
    "true_negative",
    "false_positive",
    "false_negative",
]


class ErrorAnalysisError(ValueError):
    """Raised when error-analysis inputs violate their contracts."""


@dataclass(frozen=True)
class BoundingBox:
    """Inclusive pixel-coordinate bounding box."""

    x_min: int
    y_min: int
    x_max: int
    y_max: int


@dataclass(frozen=True)
class MaskProperties:
    """Descriptive properties of a ground-truth segmentation mask."""

    available: bool
    is_empty: bool | None
    height: int | None
    width: int | None
    anomalous_pixel_count: int | None
    anomalous_area_ratio: float | None
    bounding_box: BoundingBox | None


@dataclass(frozen=True)
class ErrorAnalysisSample:
    """One test outcome and optional ground-truth mask description."""

    sample_id: str
    source_path: str
    mask_path: str | None
    label: int
    predicted_label: int
    actual_class: str
    predicted_class: str
    defect_type: str
    anomaly_score: float
    threshold: float
    has_mask: bool
    outcome: OutcomeName
    mask_properties: MaskProperties | None


@dataclass(frozen=True)
class Rankings:
    highest_scoring_normal: tuple[
        ErrorAnalysisSample,
        ...,
    ]
    lowest_scoring_anomalous: tuple[
        ErrorAnalysisSample,
        ...,
    ]
    most_confident_false_positives: tuple[
        ErrorAnalysisSample,
        ...,
    ]
    most_confident_false_negatives: tuple[
        ErrorAnalysisSample,
        ...,
    ]


@dataclass(frozen=True)
class AreaRatioSummary:
    count: int
    minimum: float
    maximum: float
    mean: float
    median: float
    standard_deviation: float


@dataclass(frozen=True)
class SmallAnomalyAnalysis:
    definition: str
    annotated_anomalous_sample_count: int
    median_area_ratio: float | None
    small_sample_count: int
    larger_sample_count: int
    small_false_negative_count: int
    larger_false_negative_count: int
    small_false_negative_rate: float | None
    larger_false_negative_rate: float | None
    true_positive_area_ratios: AreaRatioSummary | None
    false_negative_area_ratios: AreaRatioSummary | None
    observation: str


def categorize_outcome(
    *,
    label: int,
    predicted_label: int,
) -> OutcomeName:
    """Map binary actual and predicted labels to one outcome."""
    if label not in {0, 1}:
        raise ErrorAnalysisError("Actual label must be 0 or 1.")

    if predicted_label not in {0, 1}:
        raise ErrorAnalysisError("Predicted label must be 0 or 1.")

    outcomes: dict[tuple[int, int], OutcomeName] = {
        (1, 1): "true_positive",
        (0, 0): "true_negative",
        (0, 1): "false_positive",
        (1, 0): "false_negative",
    }
    return outcomes[(label, predicted_label)]


def describe_mask(mask: ArrayLike | None) -> MaskProperties:
    """Describe a binary ``(1, H, W)`` ground-truth mask."""
    if mask is None:
        return MaskProperties(
            available=False,
            is_empty=None,
            height=None,
            width=None,
            anomalous_pixel_count=None,
            anomalous_area_ratio=None,
            bounding_box=None,
        )

    mask_array = np.asarray(mask)
    if mask_array.ndim != 3 or mask_array.shape[0] != 1:
        raise ErrorAnalysisError("Mask must have shape (1, H, W).")

    unique_values = set(np.unique(mask_array).tolist())
    if not unique_values.issubset({0, 1}):
        raise ErrorAnalysisError("Mask must contain binary values 0 and 1.")

    height = int(mask_array.shape[1])
    width = int(mask_array.shape[2])
    if height <= 0 or width <= 0:
        raise ErrorAnalysisError("Mask dimensions must be positive.")

    binary_mask = mask_array[0].astype(
        np.bool_,
        copy=False,
    )
    anomalous_pixel_count = int(np.sum(binary_mask))
    area_ratio = float(anomalous_pixel_count / (height * width))

    bounding_box = None
    if anomalous_pixel_count > 0:
        y_coordinates, x_coordinates = np.nonzero(binary_mask)
        bounding_box = BoundingBox(
            x_min=int(np.min(x_coordinates)),
            y_min=int(np.min(y_coordinates)),
            x_max=int(np.max(x_coordinates)),
            y_max=int(np.max(y_coordinates)),
        )

    return MaskProperties(
        available=True,
        is_empty=anomalous_pixel_count == 0,
        height=height,
        width=width,
        anomalous_pixel_count=anomalous_pixel_count,
        anomalous_area_ratio=area_ratio,
        bounding_box=bounding_box,
    )


def rank_error_samples(
    samples: Sequence[ErrorAnalysisSample],
    *,
    limit: int,
) -> Rankings:
    """Return deterministic image-level error rankings."""
    if limit <= 0:
        raise ErrorAnalysisError("Ranking limit must be positive.")

    normal_samples = [sample for sample in samples if sample.label == 0]
    anomalous_samples = [sample for sample in samples if sample.label == 1]
    false_positives = [
        sample for sample in samples if sample.outcome == "false_positive"
    ]
    false_negatives = [
        sample for sample in samples if sample.outcome == "false_negative"
    ]

    def highest_key(
        sample: ErrorAnalysisSample,
    ) -> tuple[float, str]:
        return (-sample.anomaly_score, sample.sample_id)

    def lowest_key(
        sample: ErrorAnalysisSample,
    ) -> tuple[float, str]:
        return (sample.anomaly_score, sample.sample_id)

    return Rankings(
        highest_scoring_normal=tuple(
            sorted(
                normal_samples,
                key=highest_key,
            )[:limit]
        ),
        lowest_scoring_anomalous=tuple(
            sorted(
                anomalous_samples,
                key=lowest_key,
            )[:limit]
        ),
        most_confident_false_positives=tuple(
            sorted(
                false_positives,
                key=highest_key,
            )[:limit]
        ),
        most_confident_false_negatives=tuple(
            sorted(
                false_negatives,
                key=lowest_key,
            )[:limit]
        ),
    )


def count_outcomes(
    samples: Sequence[ErrorAnalysisSample],
) -> dict[OutcomeName, int]:
    """Count each image-level outcome."""
    counts: dict[OutcomeName, int] = {
        "true_positive": 0,
        "true_negative": 0,
        "false_positive": 0,
        "false_negative": 0,
    }

    for sample in samples:
        counts[sample.outcome] += 1

    return counts


def _area_summary(
    values: list[float],
) -> AreaRatioSummary | None:
    if not values:
        return None

    array = np.asarray(values, dtype=np.float64)
    return AreaRatioSummary(
        count=array.shape[0],
        minimum=float(np.min(array)),
        maximum=float(np.max(array)),
        mean=float(np.mean(array)),
        median=float(np.median(array)),
        standard_deviation=float(np.std(array)),
    )


def analyze_small_anomalies(
    samples: Sequence[ErrorAnalysisSample],
) -> SmallAnomalyAnalysis:
    """Compare false-negative rates below/above median mask area."""
    annotated_anomalies = [
        sample
        for sample in samples
        if (
            sample.label == 1
            and sample.mask_properties is not None
            and sample.mask_properties.available
            and (sample.mask_properties.anomalous_area_ratio is not None)
        )
    ]
    definition = (
        "Small means ground-truth anomalous area ratio at or below the "
        "median among annotated anomalous test samples."
    )

    if not annotated_anomalies:
        return SmallAnomalyAnalysis(
            definition=definition,
            annotated_anomalous_sample_count=0,
            median_area_ratio=None,
            small_sample_count=0,
            larger_sample_count=0,
            small_false_negative_count=0,
            larger_false_negative_count=0,
            small_false_negative_rate=None,
            larger_false_negative_rate=None,
            true_positive_area_ratios=None,
            false_negative_area_ratios=None,
            observation=(
                "No annotated anomalous masks were available for "
                "area-based analysis."
            ),
        )

    area_ratios = [
        float(sample.mask_properties.anomalous_area_ratio)
        for sample in annotated_anomalies
    ]
    median_area_ratio = float(
        np.median(
            np.asarray(
                area_ratios,
                dtype=np.float64,
            )
        )
    )
    small_samples = [
        sample
        for sample in annotated_anomalies
        if (sample.mask_properties.anomalous_area_ratio <= median_area_ratio)
    ]
    larger_samples = [
        sample
        for sample in annotated_anomalies
        if (sample.mask_properties.anomalous_area_ratio > median_area_ratio)
    ]
    small_false_negatives = sum(
        sample.outcome == "false_negative" for sample in small_samples
    )
    larger_false_negatives = sum(
        sample.outcome == "false_negative" for sample in larger_samples
    )
    small_false_negative_rate = float(small_false_negatives / len(small_samples))
    larger_false_negative_rate = (
        float(larger_false_negatives / len(larger_samples)) if larger_samples else None
    )

    if larger_false_negative_rate is None:
        observation = (
            "All annotated anomalies fall at the same area ratio; "
            "small-versus-larger failure rates cannot be compared."
        )
    elif small_false_negative_rate > larger_false_negative_rate:
        observation = (
            "False negatives are more frequent in the small-anomaly "
            "group in this test set."
        )
    elif small_false_negative_rate < larger_false_negative_rate:
        observation = (
            "False negatives are not more frequent in the small-anomaly "
            "group in this test set."
        )
    else:
        observation = (
            "Small and larger anomaly groups have the same false-negative "
            "rate in this test set."
        )

    true_positive_ratios = [
        float(sample.mask_properties.anomalous_area_ratio)
        for sample in annotated_anomalies
        if sample.outcome == "true_positive"
    ]
    false_negative_ratios = [
        float(sample.mask_properties.anomalous_area_ratio)
        for sample in annotated_anomalies
        if sample.outcome == "false_negative"
    ]

    return SmallAnomalyAnalysis(
        definition=definition,
        annotated_anomalous_sample_count=len(annotated_anomalies),
        median_area_ratio=median_area_ratio,
        small_sample_count=len(small_samples),
        larger_sample_count=len(larger_samples),
        small_false_negative_count=small_false_negatives,
        larger_false_negative_count=larger_false_negatives,
        small_false_negative_rate=(small_false_negative_rate),
        larger_false_negative_rate=(larger_false_negative_rate),
        true_positive_area_ratios=_area_summary(true_positive_ratios),
        false_negative_area_ratios=_area_summary(false_negative_ratios),
        observation=observation,
    )
