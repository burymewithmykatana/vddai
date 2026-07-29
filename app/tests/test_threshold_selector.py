import numpy as np
import pytest

from ml.threshold_selector import (
    THRESHOLD_POLICY_NAME,
    NormalValidationQuantileThresholdSelector,
    ThresholdSelectionError,
)


def select_threshold(
    scores,
    *,
    quantile: float = 0.5,
    labels=None,
    splits=None,
):
    score_count = len(scores)
    return (
        NormalValidationQuantileThresholdSelector()
        .select(
            validation_scores=scores,
            validation_labels=(
                labels
                if labels is not None
                else [0] * score_count
            ),
            split_metadata=(
                splits
                if splits is not None
                else ["validation"] * score_count
            ),
            quantile=quantile,
        )
    )


def test_manually_calculable_linear_quantile() -> None:
    selection = select_threshold(
        [1.0, 2.0, 3.0, 4.0],
        quantile=0.5,
    )

    assert selection.threshold == pytest.approx(2.5)
    assert selection.quantile == 0.5
    assert selection.validation_sample_count == 4
    assert selection.threshold_policy == (
        THRESHOLD_POLICY_NAME
    )
    assert selection.score_summary.minimum == 1.0
    assert selection.score_summary.maximum == 4.0
    assert selection.score_summary.mean == 2.5
    assert selection.score_summary.median == 2.5
    assert (
        selection.score_summary.standard_deviation
        == pytest.approx(np.sqrt(1.25))
    )
    assert (
        selection.estimated_validation_false_positive_rate
        == 0.5
    )


def test_score_equal_to_threshold_is_normal() -> None:
    selector = NormalValidationQuantileThresholdSelector()

    predictions = selector.classify(
        scores=[2.49, 2.5, 2.51],
        threshold=2.5,
    )

    assert predictions.tolist() == [
        False,
        False,
        True,
    ]


@pytest.mark.parametrize(
    "quantile",
    [
        -0.01,
        1.01,
        np.nan,
        np.inf,
    ],
)
def test_invalid_quantile_is_rejected(
    quantile: float,
) -> None:
    with pytest.raises(
        ThresholdSelectionError,
        match=r"\[0, 1\]",
    ):
        select_threshold(
            [1.0, 2.0],
            quantile=quantile,
        )


@pytest.mark.parametrize(
    ("quantile", "expected"),
    [
        (0.0, 1.0),
        (1.0, 4.0),
    ],
)
def test_quantile_interval_boundaries_are_valid(
    quantile: float,
    expected: float,
) -> None:
    selection = select_threshold(
        [1.0, 2.0, 3.0, 4.0],
        quantile=quantile,
    )

    assert selection.threshold == expected


def test_empty_validation_scores_are_rejected() -> None:
    with pytest.raises(
        ThresholdSelectionError,
        match="non-empty",
    ):
        select_threshold([])


@pytest.mark.parametrize(
    "scores",
    [
        [1.0, np.nan],
        [1.0, np.inf],
    ],
)
def test_non_finite_scores_are_rejected(
    scores,
) -> None:
    with pytest.raises(
        ThresholdSelectionError,
        match="finite",
    ):
        select_threshold(scores)


def test_accidental_test_split_input_is_rejected() -> None:
    with pytest.raises(
        ThresholdSelectionError,
        match="validation records only",
    ):
        select_threshold(
            [1.0, 2.0],
            splits=["validation", "test"],
        )


def test_anomalous_validation_input_is_rejected() -> None:
    with pytest.raises(
        ThresholdSelectionError,
        match="anomalous validation",
    ):
        select_threshold(
            [1.0, 2.0],
            labels=[0, 1],
        )
