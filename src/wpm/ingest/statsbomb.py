"""StatsBomb open data ingestion.

Free event-level data for a limited set of competition-seasons, including every
La Liga season from 2009/10 to 2020/21 and 2015/16 for the other big leagues.
Useful for deep event features and for validating the shot model.

Licence: StatsBomb open data — research use, attribution required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .http import HttpClient

RAW = "https://raw.githubusercontent.com/hudl/open-data/master/data"
API = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


class StatsBomb:
    def __init__(self, client: Optional[HttpClient] = None) -> None:
        self.client = client or HttpClient(min_interval=0.3)

    def competitions(self) -> pd.DataFrame:
        data = self.client.get_json(f"{RAW}/competitions.json")
        return pd.DataFrame(data)

    def matches(self, competition_id: int, season_id: int) -> pd.DataFrame:
        data = self.client.get_json(f"{RAW}/matches/{competition_id}/{season_id}.json")
        rows: List[Dict[str, Any]] = []
        for match in data:
            rows.append(
                {
                    "match_id": match.get("match_id"),
                    "date": match.get("match_date"),
                    "home": (match.get("home_team") or {}).get("home_team_name"),
                    "away": (match.get("away_team") or {}).get("away_team_name"),
                    "home_score": match.get("home_score"),
                    "away_score": match.get("away_score"),
                }
            )
        return pd.DataFrame(rows)

    def events(self, match_id: int) -> Dict[str, Any]:
        return self.client.get_json(f"{API}/events/{match_id}.json")

    def download_season(
        self,
        competition_id: int,
        season_id: int,
        out_dir: Path,
        limit: Optional[int] = None,
    ) -> int:
        out_dir.mkdir(parents=True, exist_ok=True)
        matches = self.matches(competition_id, season_id)
        if limit:
            matches = matches.head(limit)
        written = 0
        for match_id in matches["match_id"]:
            target = out_dir / f"{match_id}.json"
            if target.exists():
                continue
            events = self.events(int(match_id))
            target.write_text(json.dumps(events), encoding="utf-8")
            written += 1
        return written
