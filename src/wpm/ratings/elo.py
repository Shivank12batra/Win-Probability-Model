"""Elo ratings built from historical results.

Deliberately simple and auditable: standard Elo with a fixed home advantage,
goal-difference weighting and a mild regression to the mean at season
boundaries. Output is one row per match with *pre-match* ratings, which is what
the win probability model is allowed to see.

The three-way extension uses Davidson's model for draws, fitted on the data, so
Elo produces a full home/draw/away distribution rather than only a home-win
probability.
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from ..config import ELO_HOME_ADVANTAGE, ELO_K, ELO_SEASON_REGRESSION, ELO_START

RESULT_TO_INDEX = {"H": 0, "D": 1, "A": 2}


def _goal_multiplier(goal_difference: int) -> float:
    if goal_difference <= 1:
        return 1.0
    if goal_difference == 2:
        return 1.5
    return (11 + goal_difference) / 8.0


def rating_deviation(matches_played: int) -> float:
    """Cheap uncertainty proxy: wide for new teams, narrowing with games.

    Not a Glicko-2 deviation — a monotone stand-in that the model can consume as
    ``elo_uncertainty`` until a full Glicko implementation lands.
    """
    return 350.0 / np.sqrt(matches_played + 1.0)


def build_elo(
    matches: pd.DataFrame,
    k: float = ELO_K,
    home_advantage: float = ELO_HOME_ADVANTAGE,
    season_regression: float = ELO_SEASON_REGRESSION,
    start: float = ELO_START,
) -> pd.DataFrame:
    """Return match-level frame with pre/post ratings and rating deviation.

    Required columns: ``date``, ``season``, ``home``, ``away``, ``home_goals``,
    ``away_goals``.
    """
    frame = matches.sort_values(["date", "home"]).reset_index(drop=True)
    ratings: Dict[str, float] = {}
    played: Dict[str, int] = {}
    rows = []
    current_season = None

    for match in frame.itertuples(index=False):
        if current_season is not None and match.season != current_season:
            for team in list(ratings):
                ratings[team] = start + (ratings[team] - start) * (1 - season_regression)
        current_season = match.season

        home_rating = ratings.get(match.home, start)
        away_rating = ratings.get(match.away, start)
        home_played = played.get(match.home, 0)
        away_played = played.get(match.away, 0)

        expected_home = 1.0 / (1.0 + 10 ** (-((home_rating + home_advantage) - away_rating) / 400.0))

        if match.home_goals > match.away_goals:
            actual_home = 1.0
        elif match.home_goals == match.away_goals:
            actual_home = 0.5
        else:
            actual_home = 0.0

        multiplier = _goal_multiplier(abs(int(match.home_goals - match.away_goals)))
        delta = k * multiplier * (actual_home - expected_home)

        rows.append(
            {
                "date": match.date,
                "season": match.season,
                "league": getattr(match, "league", None),
                "home": match.home,
                "away": match.away,
                "home_goals": match.home_goals,
                "away_goals": match.away_goals,
                "result": getattr(match, "result", None),
                "elo_home_pre": round(home_rating, 2),
                "elo_away_pre": round(away_rating, 2),
                "elo_diff_pre": round(home_rating + home_advantage - away_rating, 2),
                "elo_home_win_prob": round(expected_home, 4),
                "elo_rd_home": round(rating_deviation(home_played), 2),
                "elo_rd_away": round(rating_deviation(away_played), 2),
                "matches_home": home_played,
                "matches_away": away_played,
                "elo_home_post": round(home_rating + delta, 2),
                "elo_away_post": round(away_rating - delta, 2),
            }
        )

        ratings[match.home] = home_rating + delta
        ratings[match.away] = away_rating - delta
        played[match.home] = home_played + 1
        played[match.away] = away_played + 1

    return pd.DataFrame(rows)


def elo_three_way(elo_diff, nu: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Davidson (1970) draw model on the Elo difference.

    ``elo_diff`` already includes home advantage.
    """
    difference = np.asarray(elo_diff, dtype=float)
    strength_home = 10.0 ** (difference / 400.0)
    root = np.sqrt(strength_home)
    denominator = strength_home + 1.0 + nu * root
    p_home = strength_home / denominator
    p_draw = nu * root / denominator
    p_away = 1.0 / denominator
    return p_home, p_draw, p_away


def fit_draw_parameter(
    elo_matches: pd.DataFrame,
    low: float = 0.05,
    high: float = 2.5,
    step: float = 0.005,
) -> float:
    """Choose the Davidson draw parameter that maximises observed likelihood."""
    frame = elo_matches.dropna(subset=["elo_diff_pre", "result"]).copy()
    if frame.empty:
        return 0.6
    outcomes = frame["result"].map(RESULT_TO_INDEX).to_numpy()
    mask = pd.notna(outcomes)
    frame = frame[mask]
    outcomes = outcomes[mask].astype(int)
    differences = frame["elo_diff_pre"].to_numpy(dtype=float)

    best_nu, best_ll = 0.6, -np.inf
    for nu in np.arange(low, high + step, step):
        p_home, p_draw, p_away = elo_three_way(differences, float(nu))
        probabilities = np.column_stack([p_home, p_draw, p_away])
        chosen = probabilities[np.arange(len(outcomes)), outcomes]
        log_likelihood = float(np.log(np.clip(chosen, 1e-12, 1.0)).mean())
        if log_likelihood > best_ll:
            best_ll, best_nu = log_likelihood, float(nu)
    return best_nu


def add_elo_probabilities(elo_matches: pd.DataFrame, nu: float) -> pd.DataFrame:
    out = elo_matches.copy()
    p_home, p_draw, p_away = elo_three_way(out["elo_diff_pre"], nu)
    out["elo_nu"] = nu
    out["elo_p_home"] = p_home
    out["elo_p_draw"] = p_draw
    out["elo_p_away"] = p_away
    return out


def timeline(elo_matches: pd.DataFrame) -> pd.DataFrame:
    """One row per team per match: rating before and after kickoff."""
    rows = []
    for match in elo_matches.itertuples(index=False):
        for side in ("home", "away"):
            rows.append(
                {
                    "date": match.date,
                    "season": match.season,
                    "league": match.league,
                    "team": getattr(match, side),
                    "rating_pre": getattr(match, f"elo_{side}_pre"),
                    "rating_post": getattr(match, f"elo_{side}_post"),
                    "matches_played": getattr(match, f"matches_{side}") + 1,
                    "is_home": side == "home",
                }
            )
    return pd.DataFrame(rows).sort_values(["team", "date"]).reset_index(drop=True)


def current_ratings(team_timeline: pd.DataFrame) -> pd.DataFrame:
    latest = (
        team_timeline.sort_values("date")
        .groupby("team", as_index=False)
        .tail(1)
        .sort_values("rating_post", ascending=False)
    )
    return latest[["team", "league", "date", "rating_post", "matches_played"]].rename(
        columns={"rating_post": "elo"}
    )
