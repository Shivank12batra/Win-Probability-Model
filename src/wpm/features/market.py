"""Market-implied probabilities from bookmaker odds.

Closing odds are the strongest single pre-match predictor available for free.
We remove the bookmaker margin ("de-vig") so the three probabilities sum to one.
The default power method corrects the favourite-longshot bias that simple
proportional normalisation leaves behind.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd

ODDS_COLUMNS = ["odds_home", "odds_draw", "odds_away"]
OUTPUT_COLUMNS = ["market_p_home", "market_p_draw", "market_p_away"]


def _power_devig(inverse_odds: np.ndarray) -> np.ndarray:
    """Vectorised power method: find k per row such that sum(p^k) = 1."""
    low = np.full(inverse_odds.shape[0], 0.2)
    high = np.full(inverse_odds.shape[0], 3.0)
    for _ in range(50):
        mid = (low + high) / 2
        totals = (inverse_odds ** mid[:, None]).sum(axis=1)
        too_high = totals > 1.0
        low = np.where(too_high, mid, low)
        high = np.where(too_high, high, mid)
    powered = inverse_odds ** ((low + high) / 2)[:, None]
    return powered / powered.sum(axis=1, keepdims=True)


def devig(
    odds_home: float,
    odds_draw: float,
    odds_away: float,
    method: str = "power",
) -> Tuple[float, float, float]:
    """Return (p_home, p_draw, p_away) for a single set of decimal odds."""
    odds = np.array([odds_home, odds_draw, odds_away], dtype=float)
    if not np.all(np.isfinite(odds)) or np.any(odds <= 1.0):
        return (np.nan, np.nan, np.nan)
    inverse = 1.0 / odds
    if method == "proportional":
        probabilities = inverse / inverse.sum()
    else:
        probabilities = _power_devig(inverse.reshape(1, -1))[0]
    return tuple(float(p) for p in probabilities)


def add_market_probabilities(
    frame: pd.DataFrame,
    method: str = "power",
) -> pd.DataFrame:
    """Attach ``market_p_*`` and ``overround`` columns in place-safe fashion."""
    out = frame.copy()
    missing = [c for c in ODDS_COLUMNS if c not in out.columns]
    if missing:
        for column in OUTPUT_COLUMNS:
            out[column] = np.nan
        out["overround"] = np.nan
        return out

    odds = out[ODDS_COLUMNS].to_numpy(dtype=float)
    valid = np.isfinite(odds).all(axis=1) & (odds > 1.0).all(axis=1)
    inverse = np.full_like(odds, np.nan)
    inverse[valid] = 1.0 / odds[valid]

    probabilities = np.full_like(odds, np.nan)
    if valid.any():
        if method == "proportional":
            totals = inverse[valid].sum(axis=1, keepdims=True)
            probabilities[valid] = inverse[valid] / totals
        else:
            probabilities[valid] = _power_devig(inverse[valid])

    for index, column in enumerate(OUTPUT_COLUMNS):
        out[column] = probabilities[:, index]
    out["overround"] = np.where(valid, inverse.sum(axis=1), np.nan)
    return out


def outcome_index(result: Optional[str]) -> Optional[int]:
    """Map 'H'/'D'/'A' to 0/1/2 (the ordered outcome used by RPS)."""
    return {"H": 0, "D": 1, "A": 2}.get(str(result).upper())
