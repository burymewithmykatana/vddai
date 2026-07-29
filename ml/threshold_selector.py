"""Normal-only validation quantile threshold selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray


THRESHOLD_POLICY_NAME = "normal_validation_quantile"
QUANTILE_METHOD = "linear"

BooleanArray = NDArray[np.bool_]
FloatScoreArray = NDArray[np.float64]


class ThresholdSelectionError(ValueError):
    """Raised when calibration inputs violate the threshold policy."""


@dataclass(frozen=True)
class ScoreSummary:
    """Summary statistics for normal validation scores."""

    minimum: float
    maximum: float
    mean: float
    median: float
    standard_deviation: float


@dataclass(frozen=True)
class ThresholdSelection:
    """Result of normal-only validation quantile calibration."""

    threshold: float
    quantile: float
    validation_sample_count: int
    score_summary: ScoreSummary
    estimated_validation_false_positive_rate: float
    threshold_policy: str


class NormalValidationQuantileThresholdSelector:
    """Select a threshold from normal validation scores only.

    Prediction semantics are fixed: ``score > threshold`` is anomalous and
    ``score <= threshold`` is normal.
    """

    @staticmethod
    def _validate_scores(
        scores: ArrayLike,
    ) -> FloatScoreArray:
        try:
            score_array = np.asarray(
                scores,
                dtype=np.float64,
            )
        except (TypeError, ValueError) as exc:
            raise ThresholdSelectionError(
                "Validation scores must be numeric."
            ) from exc

        if score_array.size == 0:
            raise ThresholdSelectionError(
                "Validation scores must be non-empty."
            )

        if score_array.ndim != 1:
            raise ThresholdSelectionError(
                "Validation scores must have shape (N,)."
            )

        if not np.isfinite(score_array).all():
            raise ThresholdSelectionError(
                "Validation scores must contain only finite values."
            )

        return score_array

    @staticmethod
    def _validate_quantile(quantile: float) -> float:
        try:
            validated_quantile = float(quantile)
        except (TypeError, ValueError) as exc:
            raise ThresholdSelectionError(
                "Quantile must be numeric."
            ) from exc

        if (
            not np.isfinite(validated_quantile)
            or validated_quantile < 0.0
            or validated_quantile > 1.0
        ):
            raise ThresholdSelectionError(
                "Quantile must be in the interval [0, 1]."
            )

        return validated_quantile

    def select(
        self,
        *,
        validation_scores: ArrayLike,
        validation_labels: ArrayLike,
        split_metadata: Sequence[str],
        quantile: float,
    ) -> ThresholdSelection:
        """Select a normal-only quantile threshold."""
        scores = self._validate_scores(
            validation_scores
        )
        validated_quantile = self._validate_quantile(
            quantile
        )

        labels = np.asarray(validation_labels)
        splits = np.asarray(
            split_metadata,
            dtype=np.str_,
        )

        if labels.ndim != 1:
            raise ThresholdSelectionError(
                "Validation labels must have shape (N,)."
            )

        if splits.ndim != 1:
            raise ThresholdSelectionError(
                "Split metadata must have shape (N,)."
            )

        if (
            labels.shape[0] != scores.shape[0]
            or splits.shape[0] != scores.shape[0]
        ):
            raise ThresholdSelectionError(
                "Scores, labels, and split metadata must align."
            )

        if not np.all(splits == "validation"):
            raise ThresholdSelectionError(
                "Normal-only calibration accepts validation records only."
            )

        if np.any(labels != 0):
            raise ThresholdSelectionError(
                "Normal-only calibration rejects anomalous validation "
                "samples."
            )

        threshold = float(
            np.quantile(
                scores,
                validated_quantile,
                method=QUANTILE_METHOD,
            )
        )
        predictions = self.classify(
            scores=scores,
            threshold=threshold,
        )

        return ThresholdSelection(
            threshold=threshold,
            quantile=validated_quantile,
            validation_sample_count=scores.shape[0],
            score_summary=ScoreSummary(
                minimum=float(np.min(scores)),
                maximum=float(np.max(scores)),
                mean=float(np.mean(scores)),
                median=float(np.median(scores)),
                standard_deviation=float(np.std(scores)),
            ),
            estimated_validation_false_positive_rate=float(
                np.mean(predictions)
            ),
            threshold_policy=THRESHOLD_POLICY_NAME,
        )

    def classify(
        self,
        *,
        scores: ArrayLike,
        threshold: float,
    ) -> BooleanArray:
        """Classify scores using strict greater-than anomaly semantics."""
        score_array = self._validate_scores(scores)

        try:
            validated_threshold = float(threshold)
        except (TypeError, ValueError) as exc:
            raise ThresholdSelectionError(
                "Threshold must be numeric."
            ) from exc

        if not np.isfinite(validated_threshold):
            raise ThresholdSelectionError(
                "Threshold must be finite."
            )

        return np.ascontiguousarray(
            score_array > validated_threshold,
            dtype=np.bool_,
        )
