"""football-data.co.uk ingestion.

Free historical results plus closing bookmaker odds for the top five leagues,
from the 1990s to the current season. This is the backbone for Elo ratings and
for the pre-match market prior.
"""

from __future__ import annotations

import io
from typing import Dict, Optional

import pandas as pd

from .http import HttpClient

BASE = "https://www.football-data.co.uk/mmz4281"

DIVISIONS: Dict[str, str] = {
    "E0": "EPL",
    "SP1": "LALIGA",
    "D1": "BUNDESLIGA",
    "I1": "SERIEA",
    "F1": "LIGUE1",
}

RENAME = {
    "HomeTeam": "home",
    "AwayTeam": "away",
    "FTHG": "home_goals",
    "FTAG": "away_goals",
    "FTR": "result",
    "Date": "date",
}


def season_code(start_year: int) -> str:
    """2025 -> '2526' (the 2025/26 season)."""
    return f"{str(start_year)[2:]}{str(start_year + 1)[2:]}"


class FootballData:
    def __init__(self, client: Optional[HttpClient] = None) -> None:
        self.client = client or HttpClient(min_interval=0.5)

    def season(self, division: str, start_year: int) -> pd.DataFrame:
        url = f"{BASE}/{season_code(start_year)}/{division}.csv"
        text = self.client.get_text(url)
        frame = pd.read_csv(io.StringIO(text))
        frame = frame.rename(columns=RENAME)
        keep = [c for c in ["date", "home", "away", "home_goals", "away_goals", "result"] if c in frame]
        frame = frame[keep].copy()
        frame["date"] = pd.to_datetime(frame["date"], dayfirst=True, errors="coerce")
        frame = frame.dropna(subset=["date", "home", "away", "home_goals", "away_goals"])
        frame["season"] = start_year
        frame["league"] = DIVISIONS.get(division, division)
        frame["division"] = division
        return frame

    def odds(self, division: str, start_year: int) -> pd.DataFrame:
        """Closing odds, normalised to ``odds_home/draw/away`` where available."""
        url = f"{BASE}/{season_code(start_year)}/{division}.csv"
        frame = pd.read_csv(io.StringIO(self.client.get_text(url)))
        frame = frame.rename(columns=RENAME)
        candidates = [
            ("PSCH", "PSCD", "PSCA"),
            ("B365CH", "B365CD", "B365CA"),
            ("PSH", "PSD", "PSA"),
            ("B365H", "B365D", "B365A"),
        ]
        out = pd.DataFrame({"date": pd.to_datetime(frame["date"], dayfirst=True, errors="coerce")})
        out["home"] = frame["home"]
        out["away"] = frame["away"]
        # Coalesce row-wise: use the best available book rather than dropping rows.
        for name, columns in (("odds_home", 0), ("odds_draw", 1), ("odds_away", 2)):
            series = None
            for triple in candidates:
                column = triple[columns]
                if column not in frame.columns:
                    continue
                series = frame[column] if series is None else series.combine_first(frame[column])
            out[name] = series
        return out
