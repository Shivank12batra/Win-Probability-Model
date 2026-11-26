import pandas as pd

from wpm.ratings.elo import (
    build_elo,
    elo_three_way,
    fit_draw_parameter,
    timeline,
)


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


def test_three_way_probabilities_sum_to_one():
    p_home, p_draw, p_away = elo_three_way(0.0, nu=0.7)
    assert abs(float(p_home + p_draw + p_away) - 1.0) < 1e-9
    # equal teams at a neutral venue: draw is the least likely single outcome
    assert p_draw < p_home
    assert abs(float(p_home) - float(p_away)) < 1e-9


def test_three_way_responds_to_strength():
    strong_home, _, _ = elo_three_way(200.0, nu=0.7)
    weak_home, _, _ = elo_three_way(-200.0, nu=0.7)
    assert strong_home > weak_home


def test_fit_draw_parameter_is_in_range():
    matches = pd.DataFrame(
        [
            _match("2020-08-01", 2020, "A", "B", 2, 0),
            _match("2020-08-02", 2020, "C", "D", 1, 1),
            _match("2020-08-03", 2020, "E", "F", 0, 1),
        ]
    )
    elo = build_elo(matches)
    nu = fit_draw_parameter(elo, low=0.1, high=1.0, step=0.1)
    assert 0.1 <= nu <= 1.0


def test_timeline_pre_rating_matches_previous_post_rating():
    matches = pd.DataFrame(
        [
            _match("2020-08-01", 2020, "A", "B", 2, 0),
            _match("2020-08-08", 2020, "A", "B", 1, 3),
        ]
    )
    elo = build_elo(matches, season_regression=0.0)
    rows = timeline(elo)
    team_a = rows[rows["team"] == "A"].sort_values("date")
    assert abs(team_a.iloc[1]["rating_pre"] - team_a.iloc[0]["rating_post"]) < 1e-6
