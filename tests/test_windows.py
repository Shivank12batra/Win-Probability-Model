import pandas as pd

from wpm.features.windows import build_windows


def _events():
    return pd.DataFrame(
        [
            {"type": "Goal", "minute": 12, "added": 0, "is_home": True, "card": None},
            {"type": "Card", "minute": 30, "added": 0, "is_home": True, "card": "Red"},
            {"type": "Goal", "minute": 67, "added": 0, "is_home": False, "card": None},
        ]
    )


def _shots():
    return pd.DataFrame(
        [
            {"teamId": 1, "min": 5, "minAdded": 0, "expectedGoals": 0.1},
            {"teamId": 2, "min": 20, "minAdded": 0, "expectedGoals": 0.3},
            {"teamId": 1, "min": 66, "minAdded": 0, "expectedGoals": 0.5},
        ]
    )


def test_row_count():
    frame = build_windows("Home", "Away", 1, 2, _events(), _shots())
    assert len(frame) == 36  # 18 windows x 2 teams
    assert set(frame["team"]) == {"Home", "Away"}


def test_score_state_is_backward_looking():
    frame = build_windows("Home", "Away", 1, 2, _events(), _shots())
    home = frame[(frame["team"] == "Home") & (frame["window_start"] == 15)].iloc[0]
    assert home["score_diff"] == 1
    assert home["total_goals"] == 1
    # the 67' goal must not be visible at 15'
    away = frame[(frame["team"] == "Away") & (frame["window_start"] == 15)].iloc[0]
    assert away["score_diff"] == -1


def test_target_only_counts_goals_in_window():
    frame = build_windows("Home", "Away", 1, 2, _events(), _shots())
    home_goal = frame[(frame["team"] == "Home") & (frame["window_start"] == 10)].iloc[0]
    assert home_goal["target_goals"] == 1
    away_goal = frame[(frame["team"] == "Away") & (frame["window_start"] == 65)].iloc[0]
    assert away_goal["target_goals"] == 1


def test_red_card_is_cumulative():
    frame = build_windows("Home", "Away", 1, 2, _events(), _shots())
    before = frame[(frame["team"] == "Home") & (frame["window_start"] == 25)].iloc[0]
    after = frame[(frame["team"] == "Home") & (frame["window_start"] == 35)].iloc[0]
    assert before["red_diff"] == 0
    assert after["red_diff"] == 1


def test_xg_uses_only_past_shots():
    frame = build_windows("Home", "Away", 1, 2, _events(), _shots())
    row = frame[(frame["team"] == "Home") & (frame["window_start"] == 10)].iloc[0]
    assert abs(row["xg_for"] - 0.1) < 1e-9
    assert row["xg_against"] == 0.0
