import numpy as np

from wpm.eval.metrics import (
    brier_score,
    expected_calibration_error,
    log_loss,
    ranked_probability_score,
    summarise,
)


def test_rps_is_zero_for_perfect_prediction():
    probs = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    outcomes = np.array([0, 1, 2])
    assert np.allclose(ranked_probability_score(probs, outcomes), 0.0)


def test_rps_respects_outcome_ordering():
    draw_prediction = np.array([[0.0, 1.0, 0.0]])
    away_actual = np.array([2])
    home_actual = np.array([0])
    # predicting a draw is less wrong for an away win than predicting a home win
    assert ranked_probability_score(draw_prediction, away_actual)[0] < ranked_probability_score(
        np.array([[1.0, 0.0, 0.0]]), away_actual
    )[0]
    assert ranked_probability_score(draw_prediction, home_actual)[0] < ranked_probability_score(
        np.array([[0.0, 0.0, 1.0]]), home_actual
    )[0]


def test_brier_and_log_loss_decrease_with_confidence():
    outcomes = np.array([0])
    sharp = np.array([[0.9, 0.05, 0.05]])
    flat = np.array([[0.4, 0.3, 0.3]])
    assert brier_score(sharp, outcomes)[0] < brier_score(flat, outcomes)[0]
    assert log_loss(sharp, outcomes)[0] < log_loss(flat, outcomes)[0]


def test_ece_zero_when_calibrated():
    rng = np.random.default_rng(0)
    probs = np.tile(np.array([[0.5, 0.25, 0.25]]), (1000, 1))
    outcomes = rng.choice(3, size=1000, p=[0.5, 0.25, 0.25])
    assert expected_calibration_error(probs, outcomes) < 0.05


def test_summarise_shape():
    probs = np.array([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]])
    outcomes = np.array([0, 2])
    result = summarise(probs, outcomes, "test")
    assert result["n"] == 2
    assert result["label"] == "test"
    assert set(result) == {"n", "rps", "brier", "log_loss", "ece", "label"}
