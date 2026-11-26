"""Validate the FotMob -> window-table pipeline on a stratified sample.

For each sampled match we fetch the FotMob detail payload once, derive shots and
events, build the 5-minute windows, and check that the data is internally
consistent with the football-data result.

Outputs:
  data/processed/sample/sample_matches.csv
  data/processed/sample/sample_windows.csv
  data/processed/sample/sample_failures.csv
  reports/sample_validation.md
"""

from __future__ import annotations

import argparse
import math
import traceback
from pathlib import Path

import pandas as pd

from wpm.features.windows import add_windowed_xg, build_windows
from wpm.ingest.fotmob import FotMob

ROOT = Path(__file__).resolve().parents[1]
COVERAGE = ROOT / "data" / "processed" / "reep" / "coverage_matches.csv"
MATCHES = ROOT / "data" / "processed" / "football_data" / "matches.csv"
OUT_DIR = ROOT / "data" / "processed" / "sample"
REPORT = ROOT / "reports" / "sample_validation.md"

MAX_MINUTE = 95


def sample_matches(n: int, per_group: int) -> pd.DataFrame:
    coverage = pd.read_csv(COVERAGE, parse_dates=["date"])
    coverage = coverage[coverage["fotmob_id"].notna()].copy()
    coverage["fotmob_id"] = coverage["fotmob_id"].astype("int64")

    parts = []
    for _, group in coverage.groupby(["league", "season"]):
        parts.append(group.sample(min(len(group), per_group), random_state=42))
    sample = pd.concat(parts)
    if len(sample) > n:
        sample = sample.sample(n, random_state=42)
    return sample.sort_values(["league", "season", "date"]).reset_index(drop=True)


def final_whistle(events: pd.DataFrame, window: int = 5, default: int = 95) -> int:
    if events.empty:
        return default
    minutes = pd.to_numeric(events["minute"], errors="coerce").fillna(0)
    added = pd.to_numeric(events["added"], errors="coerce").fillna(0)
    last = float((minutes + added).max())
    return int(math.ceil(last / window) * window)


def meta_from_details(details: dict) -> dict:
    general = details.get("general", {}) or {}
    home = general.get("homeTeam") or {}
    away = general.get("awayTeam") or {}
    if not home or not away:
        header = details.get("header", {}) or {}
        teams = header.get("teams", []) or []
        if len(teams) == 2:
            home = {"name": teams[0].get("name"), "id": teams[0].get("id")}
            away = {"name": teams[1].get("name"), "id": teams[1].get("id")}
    return {
        "home": home.get("name"),
        "home_id": home.get("id"),
        "away": away.get("name"),
        "away_id": away.get("id"),
        "league": general.get("leagueName"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--per-group", type=int, default=6)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    results = pd.read_csv(MATCHES, parse_dates=["date"])[
        ["date", "season", "league", "home", "away", "home_goals", "away_goals"]
    ]

    sample = sample_matches(args.limit, args.per_group)
    print(f"sampled {len(sample)} matches")

    client = FotMob()
    summary_rows = []
    window_rows = []
    failures = []

    for index, row in sample.iterrows():
        match_id = int(row["fotmob_id"])
        label = f"{row['home']} v {row['away']} ({row['date'].date()})"
        print(f"[{index + 1}/{len(sample)}] {label} fotmob={match_id}", flush=True)
        try:
            details = client.match_details(match_id)
            shots = client.shots_from_details(details)
            events = client.events_from_details(details)
            meta = meta_from_details(details)

            result = results[
                (results["date"] == row["date"])
                & (results["home"] == row["home"])
                & (results["away"] == row["away"])
            ]
            final_home = int(result.iloc[0]["home_goals"]) if not result.empty else None
            final_away = int(result.iloc[0]["away_goals"]) if not result.empty else None

            goals = events[events["type"].isin(["Goal", "OwnGoal"])] if not events.empty else events
            goals_home = int((goals["is_home"] == True).sum()) if not goals.empty else 0
            goals_away = int((goals["is_home"] == False).sum()) if not goals.empty else 0
            reds = 0
            if not events.empty and "card" in events.columns:
                reds = int(events["card"].isin(["Red", "SecondYellow"]).sum())

            windows = pd.DataFrame()
            if not events.empty and meta["home_id"] and meta["away_id"]:
                windows = build_windows(
                    home=meta["home"] or row["home"],
                    away=meta["away"] or row["away"],
                    home_id=meta["home_id"],
                    away_id=meta["away_id"],
                    events=events,
                    shots=shots,
                    window=5,
                    max_minute=MAX_MINUTE,
                    end_minute=final_whistle(events),
                    league=meta["league"] or row["league"],
                    match_id=match_id,
                )
                if not windows.empty:
                    windows = add_windowed_xg(windows, shots, meta["home_id"], meta["away_id"], window=10)
                    window_rows.append(windows)

            xg_values = pd.to_numeric(shots["expectedGoals"], errors="coerce") if not shots.empty else pd.Series(dtype=float)

            summary_rows.append(
                {
                    "league": row["league"],
                    "season": int(row["season"]),
                    "date": row["date"],
                    "home": row["home"],
                    "away": row["away"],
                    "fotmob_id": match_id,
                    "final_home": final_home,
                    "final_away": final_away,
                    "event_goals_home": goals_home,
                    "event_goals_away": goals_away,
                    "goals_consistent": final_home == goals_home and final_away == goals_away,
                    "shots": len(shots),
                    "xg": round(float(xg_values.sum()), 3) if len(xg_values) else 0.0,
                    "xg_missing": int(xg_values.isna().sum()) if len(xg_values) else 0,
                    "events": len(events),
                    "red_cards": reds,
                    "windows": len(windows),
                    "target_home": int(windows[windows["is_home"]]["target_goals"].sum()) if not windows.empty else 0,
                    "target_away": int(windows[~windows["is_home"]]["target_goals"].sum()) if not windows.empty else 0,
                    "has_momentum": "momentum" in (details.get("content", {}) or {}),
                    "has_lineup": bool((details.get("content", {}) or {}).get("lineup")),
                    "status": "ok",
                }
            )
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"  FAILED: {exc}", flush=True)
            failures.append(
                {
                    "league": row["league"],
                    "season": row["season"],
                    "date": row["date"],
                    "home": row["home"],
                    "away": row["away"],
                    "fotmob_id": match_id,
                    "error": str(exc),
                    "trace": traceback.format_exc(limit=2),
                }
            )

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT_DIR / "sample_matches.csv", index=False)
    if window_rows:
        pd.concat(window_rows, ignore_index=True).to_csv(OUT_DIR / "sample_windows.csv", index=False)
    pd.DataFrame(failures).to_csv(OUT_DIR / "sample_failures.csv", index=False)

    write_report(summary, failures, len(sample))


def write_report(summary: pd.DataFrame, failures: list, attempted: int) -> None:
    lines = ["# FotMob sample validation", ""]
    lines.append(f"Attempted: **{attempted}**. Succeeded: **{len(summary)}**. Failed: **{len(failures)}**.")
    lines.append("")

    if summary.empty:
        lines.append("No successful matches; nothing to validate.")
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return

    lines += [
        "## Core checks",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Matches with shot maps | {int((summary['shots'] > 0).sum())}/{len(summary)} |",
        f"| Matches with events | {int((summary['events'] > 0).sum())}/{len(summary)} |",
        f"| Goals consistent with final score | {int(summary['goals_consistent'].sum())}/{len(summary)} |",
        f"| Window targets reconcile with final score | {int(((summary['target_home'] == summary['final_home']) & (summary['target_away'] == summary['final_away'])).sum())}/{len(summary)} |",
        f"| Shots with xG present | {int((summary['xg_missing'] == 0).sum())}/{len(summary)} matches ({int(summary['xg_missing'].sum())} shots missing) |",
        f"| Matches with red cards | {int((summary['red_cards'] > 0).sum())} |",
        f"| Median shots per match | {summary['shots'].median():.0f} |",
        f"| Median events per match | {summary['events'].median():.0f} |",
        f"| Median window rows | {summary['windows'].median():.0f} |",
        f"| Matches with momentum | {int(summary['has_momentum'].sum())}/{len(summary)} |",
        f"| Matches with lineups | {int(summary['has_lineup'].sum())}/{len(summary)} |",
        "",
        "## By league",
        "",
        "| League | n | goals consistent | median shots | mean xG |",
        "|---|---|---|---|---|",
    ]
    for league, group in summary.groupby("league"):
        lines.append(
            f"| {league} | {len(group)} | {int(group['goals_consistent'].sum())}/{len(group)} "
            f"| {group['shots'].median():.0f} | {group['xg'].mean():.2f} |"
        )

    inconsistent = summary[~summary["goals_consistent"]]
    if not inconsistent.empty:
        lines += ["", "## Goal-count mismatches", ""]
        for row in inconsistent.itertuples(index=False):
            lines.append(
                f"- {row.home} v {row.away} ({row.date.date()}): final {row.final_home}-{row.final_away}, "
                f"events {row.event_goals_home}-{row.event_goals_away}"
            )

    empty = summary[summary["shots"] == 0]
    if not empty.empty:
        lines += ["", "## Matches with no shot map", ""]
        for row in empty.itertuples(index=False):
            lines.append(f"- {row.home} v {row.away} ({row.date.date()}) fotmob={row.fotmob_id}")

    if failures:
        lines += ["", "## Failures", ""]
        for failure in failures:
            lines.append(f"- {failure['home']} v {failure['away']} ({failure['date']}): {failure['error']}")

    lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
