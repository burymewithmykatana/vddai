import numpy as np
import pytest

from ml.evaluation import (
    ACCURACY_LIMITATION,
    AVERAGE_PRECISION_DEFINITION,
    EvaluationError,
    evaluate_image_level_scores,
    threshold_predictions,
)


def test_manually_verifiable_image_level_metrics() -> None:
    evaluation = evaluate_image_level_scores(
        test_scores=[0.1, 0.4, 0.35, 0.8],
        test_labels=[0, 0, 1, 1],
        defect_types=[
            "good",
            "good",
            "crack",
            "crack",
        ],
        threshold=0.5,
    )

    assert evaluation.positive_class_label == 1
    assert evaluation.positive_class_name == "anomalous"
    assert evaluation.score_direction == (
        "higher_is_more_anomalous"
    )
    assert evaluation.roc_auc == pytest.approx(0.75)
    assert evaluation.average_precision == pytest.approx(
        5.0 / 6.0
    )
    assert evaluation.average_precision_definition == (
        AVERAGE_PRECISION_DEFINITION
    )

    assert evaluation.precision_recall_curve.thresholds == (
        pytest.approx((0.1, 0.35, 0.4, 0.8))
    )
    assert len(
        evaluation.precision_recall_curve.precision
    ) == 5
    assert len(
        evaluation.precision_recall_curve.recall
    ) == 5

    threshold_metrics = evaluation.threshold_metrics
    assert threshold_metrics.confusion_matrix.true_negative == 2
    assert threshold_metrics.confusion_matrix.false_positive == 0
    assert threshold_metrics.confusion_matrix.false_negative == 1
    assert threshold_metrics.confusion_matrix.true_positive == 1
    assert threshold_metrics.precision == 1.0
    assert threshold_metrics.recall == 0.5
    assert threshold_metrics.f1 == pytest.approx(2.0 / 3.0)
    assert threshold_metrics.specificity == 1.0
    assert threshold_metrics.false_positive_rate == 0.0
    assert threshold_metrics.false_negative_rate == 0.5
    assert threshold_metrics.accuracy == 0.75
    assert threshold_metrics.zero_division_value == 0.0
    assert threshold_metrics.accuracy_limitation == (
        ACCURACY_LIMITATION
    )

    assert evaluation.per_defect_type["good"].count == 2
    assert (
        evaluation.per_defect_type["good"].normal_count
        == 2
    )
    assert (
        evaluation.per_defect_type["crack"].anomalous_count
        == 2
    )
    assert (
        evaluation.score_distributions["normal"].mean
        == pytest.approx(0.25)
    )
    assert (
        evaluation.score_distributions["anomalous"].mean
        == pytest.approx(0.575)
    )


def test_zero_division_metrics_are_explicitly_zero() -> None:
    evaluation = evaluate_image_level_scores(
        test_scores=[0.1, 0.2, 0.8, 0.9],
        test_labels=[0, 0, 1, 1],
        defect_types=[
            "good",
            "good",
            "crack",
            "crack",
        ],
        threshold=1.0,
    )

    metrics = evaluation.threshold_metrics
    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    assert metrics.f1 == 0.0
    assert metrics.specificity == 1.0
    assert metrics.false_positive_rate == 0.0
    assert metrics.false_negative_rate == 1.0
    assert metrics.accuracy == 0.5


def test_score_equal_to_threshold_predicts_normal() -> None:
    predictions = threshold_predictions(
        scores=[0.49, 0.5, 0.51],
        threshold=0.5,
    )

    assert predictions.tolist() == [
        False,
        False,
        True,
    ]


@pytest.mark.parametrize(
    "labels",
    [
        [0, 0, 0],
        [1, 1, 1],
    ],
)
def test_roc_auc_rejects_missing_class(
    labels: list[int],
) -> None:
    with pytest.raises(
        EvaluationError,
        match="requires both",
    ):
        evaluate_image_level_scores(
            test_scores=[0.1, 0.2, 0.3],
            test_labels=labels,
            defect_types=["good"] * 3,
            threshold=0.2,
        )


@pytest.mark.parametrize(
    "scores",
    [
        [0.1, np.nan],
        [0.1, np.inf],
    ],
)
def test_non_finite_scores_are_rejected(
    scores,
) -> None:
    with pytest.raises(
        EvaluationError,
        match="finite",
    ):
        evaluate_image_level_scores(
            test_scores=scores,
            test_labels=[0, 1],
            defect_types=["good", "crack"],
            threshold=0.5,
        )


def test_labels_are_not_silently_substituted() -> None:
    with pytest.raises(
        EvaluationError,
        match="binary values",
    ):
        evaluate_image_level_scores(
            test_scores=[0.1, 0.9],
            test_labels=[-1, 1],
            defect_types=["good", "crack"],
            threshold=0.5,
        )
