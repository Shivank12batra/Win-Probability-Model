"""Resumable FotMob backfill: match details -> shot/event data -> window table.

Usage:
  PYTHONPATH=src python3 scripts/backfill_fotmob.py --league EPL --season 2025
  PYTHONPATH=src python3 scripts/backfill_fotmob.py --limit 500
  PYTHONPATH=src python3 scripts/backfill_fotmob.py            # everything

Per match it writes data/processed/windows/{fotmob_id}.csv. Existing files are
skipped, so the job can be stopped and restarted at any time.
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import pandas as pd

from wpm.features.windows import add_windowed_xg, build_windows, final_whistle
from wpm.ingest.fotmob import FotMob

ROOT = Path(__file__).resolve().parents[1]
COVERAGE = ROOT / "data" / "processed" / "reep" / "coverage_matches.csv"
WINDOWS = ROOT / "data" / "processed" / "windows"
RAW = ROOT / "data" / "raw" / "fotmob"
STATUS = ROOT / "data" / "processed" / "backfill_status.csv"


def load_selection(leagues, seasons, limit) -> pd.DataFrame:
    frame = pd.read_csv(COVERAGE, parse_dates=["date"])
    frame = frame[frame["fotmob_id"].notna()].copy()
    frame["fotmob_id"] = frame["fotmob_id"].astype("int64")
    if leagues:
        frame = frame[frame["league"].isin(leagues)]
    if seasons:
        frame = frame[frame["season"].isin(seasons)]
    frame = frame.sort_values(["date", "league"]).reset_index(drop=True)
    if limit:
        frame = frame.head(limit)
    return frame


def flush(status_rows) -> None:
    if not status_rows:
        return
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(status_rows)
    if STATUS.exists():
        previous = pd.read_csv(STATUS)
        frame = pd.concat([previous, frame], ignore_index=True).drop_duplicates(
            subset=["fotmob_id"], keep="last"
        )
    frame.to_csv(STATUS, index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", action="append", help="repeatable, e.g. EPL")
    parser.add_argument("--season", action="append", type=int, help="repeatable, e.g. 2025")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true", help="refetch existing matches")
    parser.add_argument("--save-raw", action="store_true", help="store the compressed detail payload")
    parser.add_argument("--min-interval", type=float, default=1.2)
    args = parser.parse_args()

    WINDOWS.mkdir(parents=True, exist_ok=True)
    selection = load_selection(args.league, args.season, args.limit)
    print(f"selection: {len(selection)} matches", flush=True)

    client = FotMob(min_interval=args.min_interval)
    ok = skipped = failed = 0
    buffer = []

    for index, row in enumerate(selection.itertuples(index=False), start=1):
        match_id = int(row.fotmob_id)
        target = WINDOWS / f"{match_id}.csv"
        if target.exists() and not args.force:
            skipped += 1
            continue

        try:
            details = client.match_details(match_id)
            if args.save_raw:
                raw_dir = RAW / str(match_id)
                raw_dir.mkdir(parents=True, exist_ok=True)
                with gzip.open(raw_dir / "details.json.gz", "wt", encoding="utf-8") as handle:
                    json.dump(details, handle)

            shots = client.shots_from_details(details)
            events = client.events_from_details(details)
            meta = client.meta_from_details(details)

            windows = build_windows(
                home=meta["home"] or row.home,
                away=meta["away"] or row.away,
                home_id=meta["home_id"],
                away_id=meta["away_id"],
                events=events,
                shots=shots,
                window=5,
                end_minute=final_whistle(events),
                league=meta["league"] or row.league,
                match_id=match_id,
            )
            if windows.empty:
                raise RuntimeError("no windows produced")
            windows = add_windowed_xg(windows, shots, meta["home_id"], meta["away_id"], window=10)
            windows.to_csv(target, index=False)

            ok += 1
            buffer.append(
                {
                    "fotmob_id": match_id,
                    "league": row.league,
                    "season": int(row.season),
                    "date": row.date,
                    "home": row.home,
                    "away": row.away,
                    "status": "ok",
                    "rows": len(windows),
                    "shots": len(shots),
                    "events": len(events),
                    "error": "",
                }
            )
        except Exception as exc:  # pragma: no cover - network dependent
            failed += 1
            buffer.append(
                {
                    "fotmob_id": match_id,
                    "league": row.league,
                    "season": int(row.season),
                    "date": row.date,
                    "home": row.home,
                    "away": row.away,
                    "status": "failed",
                    "rows": 0,
                    "shots": 0,
                    "events": 0,
                    "error": str(exc)[:300],
                }
            )

        if index % 25 == 0:
            flush(buffer)
            buffer = []
            print(
                f"[{index}/{len(selection)}] ok={ok} skipped={skipped} failed={failed}",
                flush=True,
            )

    flush(buffer)
    print(f"done: ok={ok} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
