"""Build the fixed-forward-window training set.

For every match we emit one row per (5-minute window, team):

    features known at the start of the window  ->  goals scored in the window

The target is therefore a small count with a stable scale across the whole
match, which is what the Poisson likelihood expects. At inference time the same
model predicts the next window and that rate is scaled by the minutes remaining.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd

GOAL_TYPES = {"Goal", "OwnGoal", "Penalty"}
RED_CARD_TYPES = {"Red", "SecondYellow", "YellowRed"}


def _event_time(events: pd.DataFrame) -> pd.Series:
    minute = pd.to_numeric(events.get("minute"), errors="coerce").fillna(0.0)
    added = pd.to_numeric(events.get("added"), errors="coerce").fillna(0.0)
    return minute + added


def _shot_time(shots: pd.DataFrame) -> pd.Series:
    minute = pd.to_numeric(shots.get("min"), errors="coerce").fillna(0.0)
    added = pd.to_numeric(shots.get("minAdded"), errors="coerce").fillna(0.0)
    return minute + added


def final_whistle(events: pd.DataFrame, window: int = 5, default: int = 95) -> int:
    """Last event time, rounded up to the next window boundary."""
    if events.empty:
        return default
    last = float(_event_time(events).max())
    return int(math.ceil(last / window) * window)


def build_windows(
    home: str,
    away: str,
    home_id: int,
    away_id: int,
    events: pd.DataFrame,
    shots: pd.DataFrame,
    window: int = 5,
    max_minute: int = 90,
    end_minute: Optional[int] = None,
    league: Optional[str] = None,
    match_id: Optional[int] = None,
) -> pd.DataFrame:
    """Return the window-level frame for one match.

    ``end_minute`` should be the actual final whistle (including stoppage time),
    rounded up to the next window boundary. If omitted, ``max_minute`` is used.
    """
    events = events.copy()
    shots = shots.copy()
    if events.empty:
        return pd.DataFrame()

    events["t"] = _event_time(events)
    if not shots.empty:
        shots["t"] = _shot_time(shots)
        shots["xg"] = pd.to_numeric(shots.get("expectedGoals"), errors="coerce").fillna(0.0)
    else:
        shots["t"] = pd.Series(dtype=float)
        shots["xg"] = pd.Series(dtype=float)

    horizon = int(end_minute) if end_minute is not None else int(max_minute)

    goals = events[events["type"].isin(GOAL_TYPES)]
    cards = events[events["type"] == "Card"]
    reds = cards[cards["card"].isin(RED_CARD_TYPES)]
    yellows = cards[cards["card"] == "Yellow"]

    rows = []
    for start in range(0, horizon, window):
        end = start + window
        goals_before = goals[goals["t"] <= start]
        goals_in = goals[(goals["t"] > start) & (goals["t"] <= end)]

        score_home = int((goals_before["is_home"] == True).sum())  # noqa: E712
        score_away = int((goals_before["is_home"] == False).sum())  # noqa: E712
        target_home = int((goals_in["is_home"] == True).sum())  # noqa: E712
        target_away = int((goals_in["is_home"] == False).sum())  # noqa: E712

        red_home = int((reds[reds["t"] <= start]["is_home"] == True).sum())  # noqa: E712
        red_away = int((reds[reds["t"] <= start]["is_home"] == False).sum())  # noqa: E712
        yellow_home = int((yellows[yellows["t"] <= start]["is_home"] == True).sum())  # noqa: E712
        yellow_away = int((yellows[yellows["t"] <= start]["is_home"] == False).sum())  # noqa: E712

        xg_home = float(shots[(shots["teamId"] == home_id) & (shots["t"] <= start)]["xg"].sum())
        xg_away = float(shots[(shots["teamId"] == away_id) & (shots["t"] <= start)]["xg"].sum())

        for is_home in (True, False):
            team = home if is_home else away
            opponent = away if is_home else home
            rows.append(
                {
                    "match_id": match_id,
                    "league": league,
                    "window_start": start,
                    "window_end": end,
                    "team": team,
                    "opponent": opponent,
                    "is_home": is_home,
                    "minutes_remaining": horizon - start,
                    "score_diff": (score_home - score_away) if is_home else (score_away - score_home),
                    "total_goals": score_home + score_away,
                    "red_diff": (red_home - red_away) if is_home else (red_away - red_home),
                    "yellow_diff": (yellow_home - yellow_away) if is_home else (yellow_away - yellow_home),
                    "xg_for": round(xg_home if is_home else xg_away, 4),
                    "xg_against": round(xg_away if is_home else xg_home, 4),
                    "xg_diff": round((xg_home - xg_away) if is_home else (xg_away - xg_home), 4),
                    "target_goals": target_home if is_home else target_away,
                }
            )
    return pd.DataFrame(rows)


def add_windowed_xg(
    frame: pd.DataFrame,
    shots: pd.DataFrame,
    home_id: int,
    away_id: int,
    window: int = 10,
) -> pd.DataFrame:
    """Attach trailing-window xG per team, computed strictly backwards in time."""
    frame = frame.copy()
    if shots.empty:
        frame["xg_window"] = 0.0
        return frame
    shots = shots.copy()
    shots["t"] = _shot_time(shots)
    shots["xg"] = pd.to_numeric(shots.get("expectedGoals"), errors="coerce").fillna(0.0)
    values = []
    for row in frame.itertuples(index=False):
        start = max(0, row.window_start - window)
        slice_ = shots[(shots["t"] > start) & (shots["t"] <= row.window_start)]
        team_id = home_id if row.is_home else away_id
        values.append(float(slice_[slice_["teamId"] == team_id]["xg"].sum()))
    frame["xg_window"] = values
    return frame
