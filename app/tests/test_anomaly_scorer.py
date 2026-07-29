from pathlib import Path

import numpy as np
import pytest

from ml.anomaly_scorer import (
    AnomalyScoringError,
    NearestNeighborAnomalyScorer,
)


def test_exact_nearest_neighbor_and_mean_k_distances() -> None:
    feature_bank = np.asarray(
        [
            [0.0, 0.0],
            [3.0, 4.0],
        ],
        dtype=np.float32,
    )
    query = np.asarray(
        [[1.0, 0.0]],
        dtype=np.float32,
    )

    nearest_score = (
        NearestNeighborAnomalyScorer(k=1)
        .fit(feature_bank)
        .score(query)
    )
    mean_two_score = (
        NearestNeighborAnomalyScorer(k=2)
        .fit(feature_bank)
        .score(query)
    )

    assert nearest_score == pytest.approx([1.0])
    assert mean_two_score == pytest.approx(
        [(1.0 + np.sqrt(20.0)) / 2.0]
    )


def test_identical_query_has_zero_nearest_distance() -> None:
    feature_bank = np.asarray(
        [
            [2.0, -1.0],
            [4.0, 3.0],
        ],
        dtype=np.float32,
    )
    scorer = NearestNeighborAnomalyScorer().fit(
        feature_bank
    )

    scores = scorer.score([[2.0, -1.0]])

    assert scores == pytest.approx([0.0])


def test_farther_query_has_higher_score() -> None:
    scorer = NearestNeighborAnomalyScorer().fit(
        [[0.0, 0.0]]
    )

    scores = scorer.score(
        [
            [1.0, 0.0],
            [3.0, 4.0],
        ]
    )

    assert scores == pytest.approx([1.0, 5.0])
    assert scores[1] > scores[0]


def test_batch_scoring_returns_one_float_per_query() -> None:
    scorer = NearestNeighborAnomalyScorer(k=2).fit(
        [
            [0.0, 0.0],
            [2.0, 0.0],
            [4.0, 0.0],
        ]
    )

    scores = scorer.score(
        [
            [1.0, 0.0],
            [3.0, 0.0],
        ]
    )

    assert scores.shape == (2,)
    assert scores.dtype == np.float32
    assert scores == pytest.approx([1.0, 1.0])


@pytest.mark.parametrize("k", [0, -1])
def test_non_positive_k_is_rejected(k: int) -> None:
    with pytest.raises(
        AnomalyScoringError,
        match="positive",
    ):
        NearestNeighborAnomalyScorer(k=k)


def test_k_larger_than_bank_is_rejected() -> None:
    with pytest.raises(
        AnomalyScoringError,
        match="must not exceed",
    ):
        NearestNeighborAnomalyScorer(k=2).fit(
            [[0.0, 0.0]]
        )


def test_empty_feature_bank_is_rejected() -> None:
    with pytest.raises(
        AnomalyScoringError,
        match="non-empty",
    ):
        NearestNeighborAnomalyScorer().fit(
            np.empty((0, 2), dtype=np.float32)
        )


def test_feature_dimension_mismatch_is_rejected() -> None:
    scorer = NearestNeighborAnomalyScorer().fit(
        [[0.0, 0.0]]
    )

    with pytest.raises(
        AnomalyScoringError,
        match="dimensions must match",
    ):
        scorer.score([[0.0, 0.0, 0.0]])


@pytest.mark.parametrize(
    ("feature_bank", "query", "message"),
    [
        (
            [[0.0, np.nan]],
            [[0.0, 0.0]],
            "Feature bank",
        ),
        (
            [[0.0, 0.0]],
            [[np.inf, 0.0]],
            "Query features",
        ),
    ],
)
def test_non_finite_values_are_rejected(
    feature_bank,
    query,
    message: str,
) -> None:
    scorer = NearestNeighborAnomalyScorer()

    if message == "Feature bank":
        with pytest.raises(
            AnomalyScoringError,
            match=message,
        ):
            scorer.fit(feature_bank)
    else:
        scorer.fit(feature_bank)
        with pytest.raises(
            AnomalyScoringError,
            match=message,
        ):
            scorer.score(query)


def test_load_reads_generated_npz_feature_matrix(
    tmp_path: Path,
) -> None:
    feature_bank_path = tmp_path / "features.npz"
    np.savez_compressed(
        feature_bank_path,
        features=np.asarray(
            [
                [0.0, 0.0],
                [3.0, 4.0],
            ],
            dtype=np.float32,
        ),
    )

    scorer = NearestNeighborAnomalyScorer().load(
        feature_bank_path
    )

    assert scorer.bank_size == 2
    assert scorer.feature_dimension == 2
    assert scorer.score([[1.0, 0.0]]) == pytest.approx(
        [1.0]
    )
