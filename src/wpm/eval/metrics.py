"""Proper scoring rules for ordered three-way outcomes.

Outcome order is always home win (0), draw (1), away win (2). RPS is the primary
metric because it respects that ordering; ECE measures calibration directly.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def _as_probabilities(probabilities: np.ndarray) -> np.ndarray:
    array = np.asarray(probabilities, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError("probabilities must be shape (n, 3)")
    return array


def _one_hot(outcomes: np.ndarray) -> np.ndarray:
    outcomes = np.asarray(outcomes, dtype=int)
    return np.eye(3)[outcomes]


def ranked_probability_score(
    probabilities: np.ndarray,
    outcomes: np.ndarray,
) -> np.ndarray:
    """Per-row RPS. Lower is better; 0 is perfect, ~0.5 is maximally wrong."""
    probs = _as_probabilities(probabilities)
    observed = _one_hot(outcomes)
    cumulative_p = np.cumsum(probs, axis=1)[:, :2]
    cumulative_o = np.cumsum(observed, axis=1)[:, :2]
    return 0.5 * ((cumulative_p - cumulative_o) ** 2).sum(axis=1)


def brier_score(probabilities: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    probs = _as_probabilities(probabilities)
    observed = _one_hot(outcomes)
    return ((probs - observed) ** 2).sum(axis=1)


def log_loss(probabilities: np.ndarray, outcomes: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    probs = np.clip(_as_probabilities(probabilities), eps, 1.0)
    outcomes = np.asarray(outcomes, dtype=int)
    return -np.log(probs[np.arange(len(outcomes)), outcomes])


def expected_calibration_error(
    probabilities: np.ndarray,
    outcomes: np.ndarray,
    bins: int = 10,
) -> float:
    """Multiclass ECE: average gap between confidence and observed frequency."""
    probs = _as_probabilities(probabilities)
    observed = _one_hot(outcomes)
    confidence = probs.max(axis=1)
    predicted = probs.argmax(axis=1)
    correct = (predicted == np.asarray(outcomes, dtype=int)).astype(float)

    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(probs)
    error = 0.0
    for lower, upper in zip(edges[:-1], edges[1:]):
        mask = (confidence > lower) & (confidence <= upper)
        if not mask.any():
            continue
        gap = abs(correct[mask].mean() - confidence[mask].mean())
        error += (mask.sum() / total) * gap
    return float(error)


def summarise(
    probabilities: np.ndarray,
    outcomes: np.ndarray,
    label: Optional[str] = None,
) -> dict:
    rps = ranked_probability_score(probabilities, outcomes)
    brier = brier_score(probabilities, outcomes)
    loss = log_loss(probabilities, outcomes)
    result = {
        "n": int(len(outcomes)),
        "rps": float(np.mean(rps)),
        "brier": float(np.mean(brier)),
        "log_loss": float(np.mean(loss)),
        "ece": expected_calibration_error(probabilities, outcomes),
    }
    if label:
        result["label"] = label
    return result
