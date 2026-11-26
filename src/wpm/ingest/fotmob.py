"""FotMob ingestion.

FotMob is an undocumented internal JSON API. It is the primary live source:
fixtures, live clock, score, xG, shot maps with per-shot xG, momentum and events.

Verified working 2026-11. Treat every field as optional and validate before use.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from .http import HttpClient

BASE = "https://www.fotmob.com/api/data"

TOP_FIVE_HINTS = (
    "Premier League",
    "LaLiga",
    "La Liga",
    "Bundesliga",
    "Serie A",
    "Ligue 1",
)


class FotMob:
    def __init__(self, client: Optional[HttpClient] = None) -> None:
        self.client = client or HttpClient(
            min_interval=1.5,
            headers={"Referer": "https://www.fotmob.com/", "Accept": "application/json"},
        )

    # ------------------------------------------------------------------ fixtures
    def matches_on(self, date: str) -> pd.DataFrame:
        """All matches on a date. ``date`` is ``YYYYMMDD``."""
        payload = self.client.get_json(f"{BASE}/matches", params={"date": date})
        rows: List[Dict[str, Any]] = []
        for league in payload.get("leagues", []):
            for match in league.get("matches", []):
                status = match.get("status", {}) or {}
                rows.append(
                    {
                        "league": league.get("name"),
                        "league_id": league.get("id"),
                        "match_id": match.get("id"),
                        "utc_time": status.get("utcTime"),
                        "home": (match.get("home") or {}).get("name"),
                        "home_id": (match.get("home") or {}).get("id"),
                        "away": (match.get("away") or {}).get("name"),
                        "away_id": (match.get("away") or {}).get("id"),
                        "home_score": (match.get("home") or {}).get("score"),
                        "away_score": (match.get("away") or {}).get("score"),
                        "started": bool(status.get("started")),
                        "finished": bool(status.get("finished")),
                        "cancelled": bool(status.get("cancelled")),
                        "score_str": status.get("scoreStr"),
                        "reason": (status.get("reason") or {}).get("short"),
                    }
                )
        return pd.DataFrame(rows)

    def top_five_matches_on(self, date: str) -> pd.DataFrame:
        df = self.matches_on(date)
        if df.empty:
            return df
        return df[df["league"].isin(TOP_FIVE_HINTS)].reset_index(drop=True)

    def live(self, date: str) -> pd.DataFrame:
        df = self.matches_on(date)
        if df.empty:
            return df
        return df[df["started"] & ~df["finished"] & ~df["cancelled"]].reset_index(drop=True)

    # ------------------------------------------------------------------ detail
    def match_details(self, match_id: int) -> Dict[str, Any]:
        return self.client.get_json(f"{BASE}/matchDetails", params={"matchId": match_id})

    def match_meta(self, match_id: int) -> Dict[str, Any]:
        general = (self.match_details(match_id).get("general") or {})
        home = general.get("homeTeam") or {}
        away = general.get("awayTeam") or {}
        return {
            "match_id": int(general.get("matchId", match_id)),
            "league": general.get("leagueName"),
            "league_id": general.get("leagueId"),
            "round": general.get("matchRound"),
            "home": home.get("name"),
            "home_id": home.get("id"),
            "away": away.get("name"),
            "away_id": away.get("id"),
        }

    def shots(self, match_id: int) -> pd.DataFrame:
        details = self.match_details(match_id)
        shots = (details.get("content", {}) or {}).get("shotmap", {}).get("shots", []) or []
        columns = [
            "id",
            "teamId",
            "playerName",
            "min",
            "minAdded",
            "x",
            "y",
            "expectedGoals",
            "expectedGoalsOnTarget",
            "eventType",
            "situation",
            "shotType",
            "isOnTarget",
            "isBlocked",
            "isFromInsideBox",
            "period",
        ]
        if not shots:
            return pd.DataFrame(columns=columns)
        df = pd.DataFrame(shots)
        for column in columns:
            if column not in df.columns:
                df[column] = None
        return df[columns]

    def events(self, match_id: int) -> pd.DataFrame:
        details = self.match_details(match_id)
        events = (
            (details.get("content", {}) or {}).get("matchFacts", {}).get("events", {}) or {}
        ).get("events", []) or []
        rows: List[Dict[str, Any]] = []
        for event in events:
            rows.append(
                {
                    "event_id": event.get("eventId"),
                    "type": event.get("type"),
                    "minute": event.get("time"),
                    "added": event.get("overloadTime"),
                    "is_home": event.get("isHome"),
                    "player": event.get("playerName") or (event.get("player") or {}).get("name"),
                    "card": event.get("card"),
                    "home_score": event.get("homeScore"),
                    "away_score": event.get("awayScore"),
                }
            )
        return pd.DataFrame(rows)

    def live_xg(self, match_id: int) -> Dict[str, Optional[float]]:
        """Current side-by-side xG from the live stats block."""
        details = self.match_details(match_id)
        stats = ((details.get("content", {}) or {}).get("stats") or {}).get("Periods", {})
        block = (stats.get("All") or {}).get("stats", []) or []
        out: Dict[str, Optional[float]] = {"home_xg": None, "away_xg": None}
        for group in block:
            for stat in group.get("stats", []) or []:
                if stat.get("key") == "expected_goals":
                    values = stat.get("stats") or []
                    if len(values) == 2:
                        out["home_xg"] = _to_float(values[0])
                        out["away_xg"] = _to_float(values[1])
        return out


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
