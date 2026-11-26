import numpy as np
import pandas as pd

from wpm.features.market import add_market_probabilities, devig


def test_devig_probabilities_sum_to_one():
    p_home, p_draw, p_away = devig(2.0, 3.5, 4.0)
    assert abs(p_home + p_draw + p_away - 1.0) < 1e-9
    assert p_home > p_draw > p_away


def test_power_method_removes_more_margin_than_proportional():
    home, draw, away = 1.30, 5.50, 9.00
    proportional = devig(home, draw, away, method="proportional")
    power = devig(home, draw, away, method="power")
    assert abs(sum(proportional) - 1.0) < 1e-9
    assert abs(sum(power) - 1.0) < 1e-9
    # the favourite should be pushed slightly higher by the power method
    assert power[0] > proportional[0]


def test_missing_odds_become_nan():
    assert np.isnan(devig(np.nan, 3.2, 3.4)[0])
    assert np.isnan(devig(1.0, 3.2, 3.4)[0])


def test_add_market_probabilities_handles_mixed_rows():
    frame = pd.DataFrame(
        {
            "odds_home": [2.0, np.nan],
            "odds_draw": [3.5, 3.2],
            "odds_away": [4.0, 3.4],
        }
    )
    out = add_market_probabilities(frame)
    assert abs(out.loc[0, "market_p_home"] + out.loc[0, "market_p_draw"] + out.loc[0, "market_p_away"] - 1.0) < 1e-9
    assert np.isnan(out.loc[1, "market_p_home"])
    assert out.loc[0, "overround"] > 1.0
