import numpy as np
import pytest

from ml.error_analysis import (
    ErrorAnalysisSample,
    analyze_small_anomalies,
    categorize_outcome,
    describe_mask,
    rank_error_samples,
)


@pytest.mark.parametrize(
    ("label", "prediction", "expected"),
    [
        (1, 1, "true_positive"),
        (0, 0, "true_negative"),
        (0, 1, "false_positive"),
        (1, 0, "false_negative"),
    ],
)
def test_outcome_categorization(
    label: int,
    prediction: int,
    expected: str,
) -> None:
    assert (
        categorize_outcome(
            label=label,
            predicted_label=prediction,
        )
        == expected
    )


def sample(
    *,
    sample_id: str,
    label: int,
    predicted_label: int,
    score: float,
    area_ratio: float | None = None,
) -> ErrorAnalysisSample:
    mask_properties = None
    if area_ratio is not None:
        pixel_count = int(area_ratio * 100)
        mask = np.zeros(
            (1, 10, 10),
            dtype=np.uint8,
        )
        mask.reshape(-1)[:pixel_count] = 1
        mask_properties = describe_mask(mask)

    return ErrorAnalysisSample(
        sample_id=sample_id,
        source_path=f"test/good/{sample_id}.png",
        mask_path=None,
        label=label,
        predicted_label=predicted_label,
        actual_class=("anomalous" if label else "normal"),
        predicted_class=("anomalous" if predicted_label else "normal"),
        defect_type="crack" if label else "good",
        anomaly_score=score,
        threshold=0.5,
        has_mask=area_ratio is not None,
        outcome=categorize_outcome(
            label=label,
            predicted_label=predicted_label,
        ),
        mask_properties=mask_properties,
    )


def test_rankings_use_score_direction_and_stable_ties() -> None:
    samples = [
        sample(
            sample_id="normal-b",
            label=0,
            predicted_label=1,
            score=0.9,
        ),
        sample(
            sample_id="normal-a",
            label=0,
            predicted_label=1,
            score=0.9,
        ),
        sample(
            sample_id="normal-c",
            label=0,
            predicted_label=0,
            score=0.1,
        ),
        sample(
            sample_id="anomaly-b",
            label=1,
            predicted_label=0,
            score=0.2,
        ),
        sample(
            sample_id="anomaly-a",
            label=1,
            predicted_label=0,
            score=0.2,
        ),
        sample(
            sample_id="anomaly-c",
            label=1,
            predicted_label=1,
            score=0.8,
        ),
    ]

    rankings = rank_error_samples(
        samples,
        limit=3,
    )

    assert [item.sample_id for item in rankings.highest_scoring_normal] == [
        "normal-a",
        "normal-b",
        "normal-c",
    ]
    assert [item.sample_id for item in rankings.lowest_scoring_anomalous] == [
        "anomaly-a",
        "anomaly-b",
        "anomaly-c",
    ]
    assert [item.sample_id for item in (rankings.most_confident_false_positives)] == [
        "normal-a",
        "normal-b",
    ]
    assert [item.sample_id for item in (rankings.most_confident_false_negatives)] == [
        "anomaly-a",
        "anomaly-b",
    ]


def test_mask_area_ratio_and_bounding_box() -> None:
    mask = np.zeros(
        (1, 4, 4),
        dtype=np.uint8,
    )
    mask[0, 1:3, 2:4] = 1

    properties = describe_mask(mask)

    assert properties.available is True
    assert properties.is_empty is False
    assert properties.anomalous_pixel_count == 4
    assert properties.anomalous_area_ratio == 0.25
    assert properties.bounding_box is not None
    assert properties.bounding_box.x_min == 2
    assert properties.bounding_box.y_min == 1
    assert properties.bounding_box.x_max == 3
    assert properties.bounding_box.y_max == 2


def test_empty_and_absent_masks_are_distinct() -> None:
    empty = describe_mask(
        np.zeros(
            (1, 4, 4),
            dtype=np.uint8,
        )
    )
    absent = describe_mask(None)

    assert empty.available is True
    assert empty.is_empty is True
    assert empty.anomalous_pixel_count == 0
    assert empty.anomalous_area_ratio == 0.0
    assert empty.bounding_box is None

    assert absent.available is False
    assert absent.is_empty is None
    assert absent.anomalous_pixel_count is None
    assert absent.anomalous_area_ratio is None
    assert absent.bounding_box is None


def test_small_anomaly_failure_analysis() -> None:
    samples = [
        sample(
            sample_id="small-fn",
            label=1,
            predicted_label=0,
            score=0.2,
            area_ratio=0.1,
        ),
        sample(
            sample_id="large-tp",
            label=1,
            predicted_label=1,
            score=0.8,
            area_ratio=0.5,
        ),
    ]

    analysis = analyze_small_anomalies(samples)

    assert analysis.median_area_ratio == pytest.approx(0.3)
    assert analysis.small_sample_count == 1
    assert analysis.larger_sample_count == 1
    assert analysis.small_false_negative_rate == 1.0
    assert analysis.larger_false_negative_rate == 0.0
    assert analysis.false_negative_area_ratios.mean == pytest.approx(0.1)
    assert analysis.true_positive_area_ratios.mean == pytest.approx(0.5)
    assert "more frequent" in analysis.observation
