import pandas as pd

from wpm.ratings.elo import build_elo


def _match(date, season, home, away, hg, ag):
    return {
        "date": pd.Timestamp(date),
        "season": season,
        "league": "EPL",
        "home": home,
        "away": away,
        "home_goals": hg,
        "away_goals": ag,
        "result": "H" if hg > ag else ("D" if hg == ag else "A"),
    }


def test_first_match_starts_at_default():
    out = build_elo(pd.DataFrame([_match("2020-08-01", 2020, "A", "B", 2, 0)]))
    row = out.iloc[0]
    assert row["elo_home_pre"] == 1500
    assert row["elo_away_pre"] == 1500
    assert row["elo_home_win_prob"] > 0.5


def test_winner_gains_rating():
    matches = pd.DataFrame(
        [
            _match("2020-08-01", 2020, "A", "B", 2, 0),
            _match("2020-08-08", 2020, "A", "B", 1, 1),
        ]
    )
    out = build_elo(matches)
    assert out.iloc[1]["elo_home_pre"] > 1500
    assert out.iloc[1]["elo_away_pre"] < 1500


def test_season_regression_pulls_toward_mean():
    matches = pd.DataFrame(
        [
            _match("2020-08-01", 2020, "A", "B", 5, 0),
            _match("2021-08-01", 2021, "A", "B", 1, 1),
        ]
    )
    full = build_elo(matches, season_regression=1.0)
    assert full.iloc[1]["elo_home_pre"] == 1500
    assert full.iloc[1]["elo_away_pre"] == 1500

    none = build_elo(matches, season_regression=0.0)
    assert none.iloc[1]["elo_home_pre"] > 1500
