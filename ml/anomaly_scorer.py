"""Exact image-level anomaly scoring against a normal feature bank."""

from __future__ import annotations

from pathlib import Path
from typing import Self

import numpy as np
from numpy.typing import ArrayLike, NDArray


FloatFeatureArray = NDArray[np.float32]


class AnomalyScoringError(ValueError):
    """Raised when feature vectors cannot satisfy the scoring contract."""


class NearestNeighborAnomalyScorer:
    """Score queries by mean Euclidean distance to their k nearest normals."""

    def __init__(self, k: int = 1) -> None:
        if k <= 0:
            raise AnomalyScoringError(
                "k must be positive."
            )

        self.k = k
        self._feature_bank: FloatFeatureArray | None = None

    @property
    def feature_dimension(self) -> int:
        """Return the fitted feature dimension."""
        if self._feature_bank is None:
            raise AnomalyScoringError(
                "Scorer has not been fitted or loaded."
            )
        return self._feature_bank.shape[1]

    @property
    def bank_size(self) -> int:
        """Return the number of fitted normal feature vectors."""
        if self._feature_bank is None:
            raise AnomalyScoringError(
                "Scorer has not been fitted or loaded."
            )
        return self._feature_bank.shape[0]

    @staticmethod
    def _as_feature_matrix(
        values: ArrayLike,
        *,
        name: str,
    ) -> FloatFeatureArray:
        try:
            matrix = np.asarray(
                values,
                dtype=np.float32,
            )
        except (TypeError, ValueError) as exc:
            raise AnomalyScoringError(
                f"{name} must be a numeric feature matrix."
            ) from exc

        if matrix.size == 0:
            raise AnomalyScoringError(
                f"{name} must be non-empty."
            )

        if matrix.ndim != 2:
            raise AnomalyScoringError(
                f"{name} must have shape (N, D)."
            )

        if not np.isfinite(matrix).all():
            raise AnomalyScoringError(
                f"{name} must contain only finite values."
            )

        return matrix

    def fit(
        self,
        feature_bank: ArrayLike,
    ) -> Self:
        """Fit the scorer from an in-memory normal feature matrix."""
        matrix = self._as_feature_matrix(
            feature_bank,
            name="Feature bank",
        )

        if self.k > matrix.shape[0]:
            raise AnomalyScoringError(
                "k must not exceed feature-bank size."
            )

        self._feature_bank = np.array(
            matrix,
            dtype=np.float32,
            order="C",
            copy=True,
        )
        return self

    def load(self, feature_bank_path: Path) -> Self:
        """Load and fit from a feature-bank NPZ artifact."""
        try:
            with np.load(
                feature_bank_path,
                allow_pickle=False,
            ) as archive:
                feature_bank = archive["features"]
        except (OSError, KeyError, ValueError) as exc:
            raise AnomalyScoringError(
                "Feature-bank archive could not be loaded."
            ) from exc

        return self.fit(feature_bank)

    def score(
        self,
        query_features: ArrayLike,
    ) -> FloatFeatureArray:
        """Return one anomaly score per query feature vector."""
        if self._feature_bank is None:
            raise AnomalyScoringError(
                "Scorer has not been fitted or loaded."
            )

        queries = self._as_feature_matrix(
            query_features,
            name="Query features",
        )

        if queries.shape[1] != self._feature_bank.shape[1]:
            raise AnomalyScoringError(
                "Query and feature-bank dimensions must match."
            )

        differences = (
            queries[:, np.newaxis, :]
            - self._feature_bank[np.newaxis, :, :]
        )
        distances = np.linalg.norm(
            differences,
            axis=2,
        )
        nearest_distances = np.partition(
            distances,
            kth=self.k - 1,
            axis=1,
        )[:, : self.k]
        scores = nearest_distances.mean(
            axis=1,
            dtype=np.float32,
        )

        if not np.isfinite(scores).all():
            raise AnomalyScoringError(
                "Anomaly scores must contain only finite values."
            )

        return np.ascontiguousarray(
            scores,
            dtype=np.float32,
        )
