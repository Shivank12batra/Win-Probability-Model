"""Elo ratings built from historical results.

Deliberately simple and auditable: standard Elo with a fixed home advantage,
goal-difference weighting and a mild regression to the mean at season
boundaries. Output is one row per match with *pre-match* ratings, which is what
the win probability model is allowed to see.
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from ..config import ELO_HOME_ADVANTAGE, ELO_K, ELO_SEASON_REGRESSION, ELO_START


def _goal_multiplier(goal_difference: int) -> float:
    if goal_difference <= 1:
        return 1.0
    if goal_difference == 2:
        return 1.5
    return (11 + goal_difference) / 8.0


def build_elo(
    matches: pd.DataFrame,
    k: float = ELO_K,
    home_advantage: float = ELO_HOME_ADVANTAGE,
    season_regression: float = ELO_SEASON_REGRESSION,
    start: float = ELO_START,
) -> pd.DataFrame:
    """Return match-level frame with pre/post ratings.

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
                "matches_home": played.get(match.home, 0),
                "matches_away": played.get(match.away, 0),
            }
        )

        ratings[match.home] = home_rating + delta
        ratings[match.away] = away_rating - delta
        played[match.home] = played.get(match.home, 0) + 1
        played[match.away] = played.get(match.away, 0) + 1

    return pd.DataFrame(rows)
