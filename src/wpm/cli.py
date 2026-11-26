"""Command line entry point.

Examples
--------
PYTHONPATH=src python -m wpm.cli fd-elo --start 2015 --end 2025
PYTHONPATH=src python -m wpm.cli fotmob-live
PYTHONPATH=src python -m wpm.cli fotmob-match --id 4506349
PYTHONPATH=src python -m wpm.cli sb-competitions
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

from .config import DATA_DIR, ensure_dir
from .features.windows import add_windowed_xg, build_windows
from .ingest.football_data import DIVISIONS, FootballData
from .ingest.fotmob import FotMob
from .ingest.statsbomb import StatsBomb
from .ratings.elo import build_elo


def _write(frame: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    frame.to_csv(path, index=False)
    print(f"wrote {len(frame):,} rows -> {path}")


def cmd_fd_season(args: argparse.Namespace) -> None:
    client = FootballData()
    frame = client.season(args.division, args.start)
    out = Path(args.out) if args.out else DATA_DIR / "raw" / "football_data" / f"{args.division}_{args.start}.csv"
    _write(frame, out)


def cmd_fd_elo(args: argparse.Namespace) -> None:
    client = FootballData()
    frames = []
    for division in args.divisions:
        for year in range(args.start, args.end + 1):
            try:
                frame = client.season(division, year)
                if not frame.empty:
                    frames.append(frame)
                    print(f"  {division} {year}: {len(frame)} matches")
            except Exception as exc:  # pragma: no cover - network dependent
                print(f"  {division} {year}: skipped ({exc})", file=sys.stderr)
    if not frames:
        raise SystemExit("no data downloaded")
    matches = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["date", "home", "away"]
    )
    ratings = build_elo(matches)
    out = Path(args.out) if args.out else DATA_DIR / "elo" / "elo_matches.csv"
    _write(ratings, out)

    latest = ratings.sort_values("date").groupby("home").tail(1)
    print("\nlatest ratings (top 10 by pre-match Elo):")
    print(latest.sort_values("elo_home_pre", ascending=False).head(10)[["home", "elo_home_pre"]].to_string(index=False))


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

    p = sub.add_parser("fd-elo", help="build Elo ratings from football-data.co.uk")
    p.add_argument("--start", type=int, default=2015)
    p.add_argument("--end", type=int, default=2025)
    p.add_argument("--divisions", nargs="+", default=sorted(DIVISIONS))
    p.add_argument("--out")
    p.set_defaults(func=cmd_fd_elo)

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
