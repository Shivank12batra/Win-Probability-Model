"""ESPN ingestion — free, keyless fallback feed.

Gives scoreboard (live clock, score, per-team stats) and a summary endpoint with
key events, commentary containing shot coordinates, lineups and pre-match odds.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from .http import HttpClient

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"


class ESPN:
    def __init__(self, client: Optional[HttpClient] = None) -> None:
        self.client = client or HttpClient(min_interval=1.0)

    def scoreboard(self, league: str, dates: Optional[str] = None) -> pd.DataFrame:
        params = {"dates": dates} if dates else None
        payload = self.client.get_json(f"{BASE}/{league}/scoreboard", params=params)
        rows: List[Dict[str, Any]] = []
        for event in payload.get("events", []) or []:
            competition = (event.get("competitions") or [{}])[0]
            status = competition.get("status", {}) or {}
            competitors = competition.get("competitors", []) or []
            home = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away = next((c for c in competitors if c.get("homeAway") == "away"), {})
            rows.append(
                {
                    "event_id": event.get("id"),
                    "league": league,
                    "name": event.get("name"),
                    "date": event.get("date"),
                    "state": (status.get("type") or {}).get("state"),
                    "status": (status.get("type") or {}).get("name"),
                    "clock": status.get("displayClock"),
                    "period": status.get("period"),
                    "home": (home.get("team") or {}).get("displayName"),
                    "away": (away.get("team") or {}).get("displayName"),
                    "home_score": home.get("score"),
                    "away_score": away.get("score"),
                }
            )
        return pd.DataFrame(rows)

    def summary(self, league: str, event_id: str) -> Dict[str, Any]:
        return self.client.get_json(f"{BASE}/{league}/summary", params={"event": event_id})

    def team_stats(self, league: str, event_id: str) -> pd.DataFrame:
        summary = self.summary(league, event_id)
        competition = (summary.get("header", {}).get("competitions") or [{}])[0]
        rows: List[Dict[str, Any]] = []
        for competitor in competition.get("competitors", []) or []:
            team = (competitor.get("team") or {}).get("displayName")
            for stat in competitor.get("statistics", []) or []:
                rows.append(
                    {
                        "team": team,
                        "metric": stat.get("name"),
                        "value": stat.get("displayValue"),
                    }
                )
        return pd.DataFrame(rows)

    def shot_events(self, league: str, event_id: str) -> pd.DataFrame:
        """Shots parsed from commentary, including field coordinates."""
        summary = self.summary(league, event_id)
        rows: List[Dict[str, Any]] = []
        for item in summary.get("commentary", []) or []:
            play = item.get("play", {}) or {}
            play_type = (play.get("type") or {}).get("type", "")
            if "shot" not in play_type and "goal" not in play_type:
                continue
            rows.append(
                {
                    "sequence": item.get("sequence"),
                    "minute": (play.get("clock") or {}).get("value"),
                    "text": play.get("text"),
                    "type": play_type,
                    "team": (play.get("team") or {}).get("displayName"),
                    "field_x": play.get("fieldPositionX"),
                    "field_y": play.get("fieldPositionY"),
                    "goal_y": play.get("goalPositionY"),
                }
            )
        return pd.DataFrame(rows)
