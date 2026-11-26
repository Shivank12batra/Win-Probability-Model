"""Command line entry point.

Examples
--------
PYTHONPATH=src python -m wpm.cli fd-build --start 2000 --end 2025
PYTHONPATH=src python -m wpm.cli fotmob-live
PYTHONPATH=src python -m wpm.cli build-windows --id 4506349
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

from .config import DATA_DIR, ROOT, ensure_dir
from .eval.metrics import summarise
from .features.market import add_market_probabilities, outcome_index
from .features.windows import add_windowed_xg, build_windows
from .ingest.football_data import DIVISIONS, FootballData
from .ingest.fotmob import FotMob
from .ingest.statsbomb import StatsBomb
from .ratings.elo import (
    add_elo_probabilities,
    build_elo,
    current_ratings,
    fit_draw_parameter,
    timeline,
)

PROBABILITY_COLUMNS = ["market_p_home", "market_p_draw", "market_p_away"]


def _write(frame: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    frame.to_csv(path, index=False)
    print(f"wrote {len(frame):,} rows -> {path}")


def _build_prior(args: argparse.Namespace) -> Tuple[pd.DataFrame, pd.DataFrame]:
    client = FootballData()
    matches = client.many(args.divisions, args.start, args.end)
    matches = add_market_probabilities(matches)
    elo = build_elo(matches)
    return matches, elo


def _comparison(elo: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    market = matches[
        ["date", "home", "away", "season"] + PROBABILITY_COLUMNS
    ]
    merged = elo.merge(market, on=["date", "home", "away", "season"], how="inner")
    merged = merged.dropna(subset=PROBABILITY_COLUMNS + ["result"])
    return merged


def cmd_fd_elo(args: argparse.Namespace) -> None:
    _, elo = _build_prior(args)
    nu = fit_draw_parameter(elo)
    elo = add_elo_probabilities(elo, nu)
    out = Path(args.out) if args.out else DATA_DIR / "elo" / "elo_matches.csv"
    _write(elo, out)
    print(f"fitted draw parameter nu={nu:.3f}")

    latest = current_ratings(timeline(elo))
    print("\nlatest ratings (top 10):")
    print(latest.head(10).to_string(index=False))


def cmd_fd_build(args: argparse.Namespace) -> None:
    matches, elo = _build_prior(args)

    # Fit the single draw parameter only on seasons before the evaluation window.
    training = elo[elo["season"] < args.eval_start]
    nu = fit_draw_parameter(training if len(training) >= 1000 else elo)
    elo = add_elo_probabilities(elo, nu)

    out_dir = ensure_dir(Path(args.out_dir) if args.out_dir else DATA_DIR / "processed" / "football_data")

    _write(matches, out_dir / "matches.csv")
    _write(elo, out_dir / "elo_matches.csv")
    team_timeline = timeline(elo)
    _write(team_timeline, out_dir / "elo_timeline.csv")
    snapshot = current_ratings(team_timeline)
    _write(snapshot, out_dir / "elo_current.csv")

    merged = _comparison(elo, matches)
    merged = merged[merged["season"] >= args.eval_start]
    rows = []
    if merged.empty:
        print("no rows in the evaluation window; skipping evaluation")
        return

    outcomes = merged["result"].map(outcome_index).to_numpy()
    keep = pd.notna(outcomes)
    merged = merged[keep]
    outcomes = outcomes[keep].astype(int)

    for label, columns in (
        ("market", PROBABILITY_COLUMNS),
        ("elo", ["elo_p_home", "elo_p_draw", "elo_p_away"]),
    ):
        stats = summarise(merged[columns].to_numpy(dtype=float), outcomes, label)
        rows.append(stats)

    report = pd.DataFrame(rows)[["label", "n", "rps", "brier", "log_loss", "ece"]]
    print("\npre-match baseline (walk-forward, closing odds as market):")
    print(report.to_string(index=False))

    by_season = []
    for season, group in merged.groupby("season"):
        season_outcomes = group["result"].map(outcome_index).to_numpy().astype(int)
        by_season.append(
            {
                "season": int(season),
                "n": len(group),
                "market_rps": summarise(group[PROBABILITY_COLUMNS].to_numpy(float), season_outcomes)["rps"],
                "elo_rps": summarise(
                    group[["elo_p_home", "elo_p_draw", "elo_p_away"]].to_numpy(float), season_outcomes
                )["rps"],
            }
        )
    season_table = pd.DataFrame(by_season).sort_values("season")
    _write(season_table, out_dir / "prior_by_season.csv")

    _write_report(report, season_table, nu, merged, args.eval_start)
    print(f"fitted draw parameter nu={nu:.3f}")


def _md_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join(["---"] * len(columns)) + "|",
    ]
    for row in frame.itertuples(index=False):
        cells = []
        for value in row:
            cells.append(f"{value:.4f}" if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _write_report(
    report: pd.DataFrame,
    season_table: pd.DataFrame,
    nu: float,
    merged: pd.DataFrame,
    eval_start: int,
) -> None:
    path = ROOT / "reports" / "prior_baseline.md"
    ensure_dir(path.parent)
    lines = [
        "# Pre-match baseline: Elo vs market",
        "",
        f"Generated by `wpm fd-build`. Evaluation matches: {len(merged):,} "
        f"(seasons {eval_start}–{int(merged['season'].max())}). Davidson nu: {nu:.3f}.",
        "",
        "`nu` is fitted only on seasons before the evaluation window.",
        "",
        "## Overall",
        "",
        _md_table(report),
        "",
        "## By season",
        "",
        _md_table(season_table.tail(15)),
        "",
        "Notes:",
        "",
        "- Elo is built only from results available before each kickoff (no leakage).",
        "- Market probabilities are de-vigged closing odds (power method).",
        "- The market should beat Elo; that is the point of using it as a prior/feature.",
        "- Differences are largest in earlier seasons, where Elo has less history.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote report -> {path}")


def cmd_fd_season(args: argparse.Namespace) -> None:
    client = FootballData()
    frame = client.season(args.division, args.start)
    out = Path(args.out) if args.out else DATA_DIR / "raw" / "football_data" / f"{args.division}_{args.start}.csv"
    _write(frame, out)


def cmd_fotmob_day(args: argparse.Namespace) -> None:
    client = FotMob()
    frame = client.top_five_matches_on(args.date)
    out = Path(args.out) if args.out else DATA_DIR / "raw" / "fotmob" / f"matches_{args.date}.csv"
    _write(frame, out)


def cmd_fotmob_live(args: argparse.Namespace) -> None:
    client = FotMob()
    date = args.date or dt.datetime.utcnow().strftime("%Y%m%d")
    frame = client.live(date)
    if frame.empty:
        print(f"no live matches on {date}")
        return
    out = Path(args.out) if args.out else DATA_DIR / "live" / f"live_{date}.csv"
    _write(frame, out)
    print(frame[["league", "home", "home_score", "away_score", "away", "score_str"]].to_string(index=False))


def cmd_fotmob_match(args: argparse.Namespace) -> None:
    client = FotMob()
    out_dir = ensure_dir(Path(args.out) if args.out else DATA_DIR / "raw" / "fotmob" / str(args.id))
    shots = client.shots(args.id)
    events = client.events(args.id)
    _write(shots, out_dir / "shots.csv")
    _write(events, out_dir / "events.csv")
    live = client.live_xg(args.id)
    print(f"live xG: {live}")


def cmd_build_windows(args: argparse.Namespace) -> None:
    client = FotMob()
    meta = client.match_meta(args.id)
    shots = client.shots(args.id)
    events = client.events(args.id)
    frame = build_windows(
        home=meta["home"],
        away=meta["away"],
        home_id=meta["home_id"],
        away_id=meta["away_id"],
        events=events,
        shots=shots,
        window=args.window,
        league=meta["league"],
        match_id=meta["match_id"],
    )
    frame = add_windowed_xg(frame, shots, meta["home_id"], meta["away_id"], window=10)
    out = Path(args.out) if args.out else DATA_DIR / "processed" / f"windows_{args.id}.csv"
    _write(frame, out)
    print(frame.head(6).to_string(index=False))


def cmd_sb_competitions(args: argparse.Namespace) -> None:
    client = StatsBomb()
    frame = client.competitions()
    out = Path(args.out) if args.out else DATA_DIR / "raw" / "statsbomb" / "competitions.csv"
    _write(frame, out)


def cmd_sb_season(args: argparse.Namespace) -> None:
    client = StatsBomb()
    out_dir = Path(args.out) if args.out else DATA_DIR / "raw" / "statsbomb" / f"{args.comp}_{args.season}"
    written = client.download_season(args.comp, args.season, out_dir, limit=args.limit)
    print(f"downloaded {written} match event files -> {out_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wpm", description="Win probability model tooling")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fd-season", help="download one football-data.co.uk season")
    p.add_argument("--division", default="E0", choices=sorted(DIVISIONS))
    p.add_argument("--start", type=int, required=True, help="season start year, e.g. 2025")
    p.add_argument("--out")
    p.set_defaults(func=cmd_fd_season)

    p = sub.add_parser("fd-elo", help="build running Elo ratings only")
    p.add_argument("--start", type=int, default=2000)
    p.add_argument("--end", type=int, default=2025)
    p.add_argument("--divisions", nargs="+", default=sorted(DIVISIONS))
    p.add_argument("--out")
    p.set_defaults(func=cmd_fd_elo)

    p = sub.add_parser("fd-build", help="results + odds + running Elo + market prior + report")
    p.add_argument("--start", type=int, default=2000)
    p.add_argument("--end", type=int, default=2025)
    p.add_argument("--divisions", nargs="+", default=sorted(DIVISIONS))
    p.add_argument("--eval-start", type=int, default=2020)
    p.add_argument("--out-dir")
    p.set_defaults(func=cmd_fd_build)

    p = sub.add_parser("fotmob-day", help="list top-five matches for a date")
    p.add_argument("--date", required=True, help="YYYYMMDD")
    p.add_argument("--out")
    p.set_defaults(func=cmd_fotmob_day)

    p = sub.add_parser("fotmob-live", help="list live matches")
    p.add_argument("--date", help="YYYYMMDD (default: today UTC)")
    p.add_argument("--out")
    p.set_defaults(func=cmd_fotmob_live)

    p = sub.add_parser("fotmob-match", help="download shots and events for one match")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_fotmob_match)

    p = sub.add_parser("build-windows", help="build the fixed-window training rows for one match")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--window", type=int, default=5)
    p.add_argument("--out")
    p.set_defaults(func=cmd_build_windows)

    p = sub.add_parser("sb-competitions", help="list StatsBomb open competitions")
    p.add_argument("--out")
    p.set_defaults(func=cmd_sb_competitions)

    p = sub.add_parser("sb-season", help="download StatsBomb event data for a season")
    p.add_argument("--comp", type=int, required=True)
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--out")
    p.set_defaults(func=cmd_sb_season)

    return parser


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
