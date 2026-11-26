"""football-data.co.uk ingestion.

Free historical results plus closing bookmaker odds for the top five leagues,
from the 1990s to the current season. This is the backbone for Elo ratings and
for the pre-match market prior.
"""

from __future__ import annotations

import io
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import DATA_DIR, ensure_dir
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

# Closing odds, best first. Coalesced row-wise so a missing book never drops a match.
ODDS_CANDIDATES = [
    ("PSCH", "PSCD", "PSCA"),
    ("B365CH", "B365CD", "B365CA"),
    ("PSH", "PSD", "PSA"),
    ("B365H", "B365D", "B365A"),
    ("AvgCH", "AvgCD", "AvgCA"),
    ("AvgH", "AvgD", "AvgA"),
]

RESULT_COLUMNS = [
    "date",
    "season",
    "league",
    "division",
    "home",
    "away",
    "home_goals",
    "away_goals",
    "result",
    "odds_home",
    "odds_draw",
    "odds_away",
]


def season_code(start_year: int) -> str:
    """2025 -> '2526' (the 2025/26 season)."""
    return f"{str(start_year)[2:]}{str(start_year + 1)[2:]}"


class FootballData:
    def __init__(self, client: Optional[HttpClient] = None) -> None:
        self.client = client or HttpClient(min_interval=0.5)
        self._cache: Dict[tuple, pd.DataFrame] = {}

    def _read(self, division: str, start_year: int) -> pd.DataFrame:
        key = (division, start_year)
        if key in self._cache:
            return self._cache[key]

        cache_path = DATA_DIR / "raw" / "football_data" / f"{division}_{start_year}.csv"
        if cache_path.exists():
            raw = pd.read_csv(cache_path, on_bad_lines="skip")
        else:
            url = f"{BASE}/{season_code(start_year)}/{division}.csv"
            text = self.client.get_text(url)
            raw = pd.read_csv(io.StringIO(text), on_bad_lines="skip")
            ensure_dir(cache_path.parent)
            raw.to_csv(cache_path, index=False)

        self._cache[key] = raw
        return raw

    def _normalise(self, raw: pd.DataFrame, division: str, start_year: int) -> pd.DataFrame:
        frame = raw.rename(columns=RENAME).copy()

        if "result" not in frame.columns:
            frame["result"] = np.where(
                frame["home_goals"] > frame["away_goals"],
                "H",
                np.where(frame["home_goals"] == frame["away_goals"], "D", "A"),
            )

        frame["date"] = pd.to_datetime(frame["date"], dayfirst=True, errors="coerce")
        frame = frame.dropna(subset=["date", "home", "away", "home_goals", "away_goals"])

        for name, index in (("odds_home", 0), ("odds_draw", 1), ("odds_away", 2)):
            series = None
            for triple in ODDS_CANDIDATES:
                column = triple[index]
                if column not in raw.columns:
                    continue
                values = pd.to_numeric(raw[column], errors="coerce")
                series = values if series is None else series.combine_first(values)
            frame[name] = series.reindex(frame.index) if series is not None else np.nan

        frame["season"] = start_year
        frame["league"] = DIVISIONS.get(division, division)
        frame["division"] = division
        return frame[RESULT_COLUMNS].reset_index(drop=True)

    def season(self, division: str, start_year: int) -> pd.DataFrame:
        return self._normalise(self._read(division, start_year), division, start_year)

    def season_full(self, division: str, start_year: int) -> pd.DataFrame:
        """Results plus odds in one frame."""
        return self._normalise(self._read(division, start_year), division, start_year)

    def odds(self, division: str, start_year: int) -> pd.DataFrame:
        full = self.season_full(division, start_year)
        return full[["date", "home", "away", "odds_home", "odds_draw", "odds_away"]]

    def many(
        self,
        divisions: Optional[List[str]] = None,
        start: int = 2000,
        end: int = 2025,
        verbose: bool = True,
    ) -> pd.DataFrame:
        frames = []
        for division in divisions or sorted(DIVISIONS):
            for year in range(start, end + 1):
                try:
                    frame = self.season_full(division, year)
                except Exception as exc:  # pragma: no cover - network dependent
                    if verbose:
                        print(f"  {division} {year}: skipped ({exc})")
                    continue
                if frame.empty:
                    continue
                frames.append(frame)
                if verbose:
                    print(f"  {division} {year}: {len(frame)} matches")
        if not frames:
            raise RuntimeError("no football-data seasons downloaded")
        combined = pd.concat(frames, ignore_index=True)
        return combined.drop_duplicates(subset=["date", "home", "away"], keep="last")
