"""Image-level anomaly-detection evaluation metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
)


AVERAGE_PRECISION_DEFINITION = (
    "Non-interpolated average precision: the weighted mean of precision "
    "at each threshold, using each increase in recall as the weight."
)
ACCURACY_LIMITATION = (
    "Accuracy can be misleading under class imbalance because majority-class "
    "predictions may dominate the aggregate."
)

BooleanArray = NDArray[np.bool_]
FloatScoreArray = NDArray[np.float64]
IntegerLabelArray = NDArray[np.int64]


class EvaluationError(ValueError):
    """Raised when test inputs cannot support valid evaluation."""


@dataclass(frozen=True)
class ScoreDistributionSummary:
    count: int
    minimum: float
    maximum: float
    mean: float
    median: float
    standard_deviation: float


@dataclass(frozen=True)
class ConfusionMatrix:
    true_negative: int
    false_positive: int
    false_negative: int
    true_positive: int


@dataclass(frozen=True)
class ThresholdMetrics:
    threshold: float
    confusion_matrix: ConfusionMatrix
    precision: float
    recall: float
    f1: float
    specificity: float
    false_positive_rate: float
    false_negative_rate: float
    accuracy: float
    zero_division_value: float
    accuracy_limitation: str


@dataclass(frozen=True)
class PrecisionRecallCurveData:
    precision: tuple[float, ...]
    recall: tuple[float, ...]
    thresholds: tuple[float, ...]


@dataclass(frozen=True)
class DefectTypeSummary:
    count: int
    normal_count: int
    anomalous_count: int
    scores: ScoreDistributionSummary


@dataclass(frozen=True)
class ImageLevelEvaluation:
    sample_count: int
    positive_class_label: int
    positive_class_name: str
    score_direction: str
    roc_auc: float
    precision_recall_curve: PrecisionRecallCurveData
    average_precision: float
    average_precision_definition: str
    threshold_metrics: ThresholdMetrics
    per_defect_type: dict[str, DefectTypeSummary]
    score_distributions: dict[
        str,
        ScoreDistributionSummary,
    ]


def _validate_scores(scores: ArrayLike) -> FloatScoreArray:
    try:
        score_array = np.asarray(
            scores,
            dtype=np.float64,
        )
    except (TypeError, ValueError) as exc:
        raise EvaluationError(
            "Test scores must be numeric."
        ) from exc

    if score_array.size == 0:
        raise EvaluationError(
            "Test scores must be non-empty."
        )

    if score_array.ndim != 1:
        raise EvaluationError(
            "Test scores must have shape (N,)."
        )

    if not np.isfinite(score_array).all():
        raise EvaluationError(
            "Test scores must contain only finite values."
        )

    return score_array


def _validate_labels(
    labels: ArrayLike,
    expected_count: int,
) -> IntegerLabelArray:
    try:
        numeric_labels = np.asarray(
            labels,
            dtype=np.float64,
        )
    except (TypeError, ValueError) as exc:
        raise EvaluationError(
            "Test labels must be numeric binary values."
        ) from exc

    if numeric_labels.ndim != 1:
        raise EvaluationError(
            "Test labels must have shape (N,)."
        )

    if numeric_labels.shape[0] != expected_count:
        raise EvaluationError(
            "Test scores and labels must align."
        )

    if (
        not np.isfinite(numeric_labels).all()
        or not np.isin(numeric_labels, [0.0, 1.0]).all()
    ):
        raise EvaluationError(
            "Test labels must use binary values 0 and 1."
        )

    label_array = numeric_labels.astype(
        np.int64,
        copy=False,
    )

    if set(label_array.tolist()) != {0, 1}:
        raise EvaluationError(
            "ROC-AUC requires both normal and anomalous test classes."
        )

    return label_array


def _score_summary(
    scores: FloatScoreArray,
) -> ScoreDistributionSummary:
    return ScoreDistributionSummary(
        count=scores.shape[0],
        minimum=float(np.min(scores)),
        maximum=float(np.max(scores)),
        mean=float(np.mean(scores)),
        median=float(np.median(scores)),
        standard_deviation=float(np.std(scores)),
    )


def _safe_divide(
    numerator: int | float,
    denominator: int | float,
) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def threshold_predictions(
    *,
    scores: ArrayLike,
    threshold: float,
) -> BooleanArray:
    """Return anomaly predictions using strict greater-than semantics."""
    score_array = _validate_scores(scores)

    try:
        validated_threshold = float(threshold)
    except (TypeError, ValueError) as exc:
        raise EvaluationError(
            "Threshold must be numeric."
        ) from exc

    if not np.isfinite(validated_threshold):
        raise EvaluationError(
            "Threshold must be finite."
        )

    return np.ascontiguousarray(
        score_array > validated_threshold,
        dtype=np.bool_,
    )


def evaluate_image_level_scores(
    *,
    test_scores: ArrayLike,
    test_labels: ArrayLike,
    defect_types: Sequence[str],
    threshold: float,
) -> ImageLevelEvaluation:
    """Evaluate official-test image scores without tuning any inputs."""
    scores = _validate_scores(test_scores)
    labels = _validate_labels(
        test_labels,
        expected_count=scores.shape[0],
    )
    defects = np.asarray(
        defect_types,
        dtype=np.str_,
    )

    if (
        defects.ndim != 1
        or defects.shape[0] != scores.shape[0]
    ):
        raise EvaluationError(
            "Defect types must align with test scores."
        )

    predictions = threshold_predictions(
        scores=scores,
        threshold=threshold,
    )
    predicted_labels = predictions.astype(
        np.int64,
        copy=False,
    )

    true_negative = int(
        np.sum((labels == 0) & (predicted_labels == 0))
    )
    false_positive = int(
        np.sum((labels == 0) & (predicted_labels == 1))
    )
    false_negative = int(
        np.sum((labels == 1) & (predicted_labels == 0))
    )
    true_positive = int(
        np.sum((labels == 1) & (predicted_labels == 1))
    )

    precision = _safe_divide(
        true_positive,
        true_positive + false_positive,
    )
    recall = _safe_divide(
        true_positive,
        true_positive + false_negative,
    )
    f1 = _safe_divide(
        2.0 * precision * recall,
        precision + recall,
    )
    specificity = _safe_divide(
        true_negative,
        true_negative + false_positive,
    )
    false_positive_rate = _safe_divide(
        false_positive,
        false_positive + true_negative,
    )
    false_negative_rate = _safe_divide(
        false_negative,
        false_negative + true_positive,
    )
    accuracy = _safe_divide(
        true_positive + true_negative,
        scores.shape[0],
    )

    curve_precision, curve_recall, curve_thresholds = (
        precision_recall_curve(
            labels,
            scores,
            pos_label=1,
        )
    )

    per_defect_type: dict[str, DefectTypeSummary] = {}
    for defect_type in sorted(set(defects.tolist())):
        defect_mask = defects == defect_type
        defect_labels = labels[defect_mask]
        per_defect_type[defect_type] = DefectTypeSummary(
            count=int(np.sum(defect_mask)),
            normal_count=int(np.sum(defect_labels == 0)),
            anomalous_count=int(
                np.sum(defect_labels == 1)
            ),
            scores=_score_summary(scores[defect_mask]),
        )

    return ImageLevelEvaluation(
        sample_count=scores.shape[0],
        positive_class_label=1,
        positive_class_name="anomalous",
        score_direction="higher_is_more_anomalous",
        roc_auc=float(
            roc_auc_score(labels, scores)
        ),
        precision_recall_curve=PrecisionRecallCurveData(
            precision=tuple(
                float(value)
                for value in curve_precision
            ),
            recall=tuple(
                float(value)
                for value in curve_recall
            ),
            thresholds=tuple(
                float(value)
                for value in curve_thresholds
            ),
        ),
        average_precision=float(
            average_precision_score(
                labels,
                scores,
            )
        ),
        average_precision_definition=(
            AVERAGE_PRECISION_DEFINITION
        ),
        threshold_metrics=ThresholdMetrics(
            threshold=float(threshold),
            confusion_matrix=ConfusionMatrix(
                true_negative=true_negative,
                false_positive=false_positive,
                false_negative=false_negative,
                true_positive=true_positive,
            ),
            precision=precision,
            recall=recall,
            f1=f1,
            specificity=specificity,
            false_positive_rate=false_positive_rate,
            false_negative_rate=false_negative_rate,
            accuracy=accuracy,
            zero_division_value=0.0,
            accuracy_limitation=ACCURACY_LIMITATION,
        ),
        per_defect_type=per_defect_type,
        score_distributions={
            "normal": _score_summary(
                scores[labels == 0]
            ),
            "anomalous": _score_summary(
                scores[labels == 1]
            ),
        },
    )
