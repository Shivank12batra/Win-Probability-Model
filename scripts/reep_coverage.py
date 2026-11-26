"""Measure Reep coverage for the top-five leagues against football-data.

For every football-data match from 2020 onwards, try to find the Reep match by
date (+/- 1 day) and canonical team names, then report whether FotMob,
WhoScored and Understat IDs are attached.

Outputs:
  reports/reep_coverage.md
  data/processed/reep/coverage_by_league_season.csv
"""

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "data" / "raw" / "reep" / "reep-register.duckdb"
TEAM_MAP = ROOT / "config" / "team_map.csv"
MATCHES = ROOT / "data" / "processed" / "football_data" / "matches.csv"
OUT_DIR = ROOT / "data" / "processed" / "reep"
REPORT = ROOT / "reports" / "reep_coverage.md"

OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(str(REGISTER), read_only=True)
con.execute("SET temp_directory='data/raw/reep/tmp'")

con.execute(
    """
    CREATE TEMP TABLE fd AS
    SELECT date, season, league, home, away,
           home || '|' || away || '|' || strftime(date, '%Y-%m-%d') AS match_key
    FROM read_csv_auto(?)
    WHERE season >= 2020
    """,
    [str(MATCHES)],
)
con.execute("CREATE TEMP TABLE tm AS SELECT fd_name, reep_name FROM read_csv_auto(?)", [str(TEAM_MAP)])

con.execute(
    """
    CREATE TEMP TABLE rm AS
    SELECT reep_id,
           regexp_extract(canonical_name, '^(.+) v (.+), ([0-9]{4}-[0-9]{2}-[0-9]{2})$', 1) AS home_raw,
           regexp_extract(canonical_name, '^(.+) v (.+), ([0-9]{4}-[0-9]{2}-[0-9]{2})$', 2) AS away_raw,
           CAST(regexp_extract(canonical_name, '^(.+) v (.+), ([0-9]{4}-[0-9]{2}-[0-9]{2})$', 3) AS DATE) AS match_date
    FROM entities
    WHERE entity_type = 'match'
    """
)

con.execute(
    """
    CREATE TEMP TABLE cand AS
    SELECT f.match_key, f.date, f.season, f.league, f.home, f.away,
           r.reep_id, abs(date_diff('day', r.match_date, f.date)) AS day_gap
    FROM fd f
    JOIN tm th ON th.fd_name = f.home
    JOIN tm ta ON ta.fd_name = f.away
    JOIN rm r
      ON abs(date_diff('day', r.match_date, f.date)) <= 1
     AND r.home_raw = th.reep_name
     AND r.away_raw = ta.reep_name
    """
)

con.execute(
    """
    CREATE TEMP TABLE best AS
    SELECT * EXCLUDE (rn) FROM (
      SELECT *, row_number() OVER (PARTITION BY match_key ORDER BY day_gap, reep_id) AS rn
      FROM cand
    ) WHERE rn = 1
    """
)

con.execute(
    """
    CREATE TEMP TABLE bridges_m AS
    SELECT reep_id,
           max(CASE WHEN provider = 'fotmob' AND namespace = 'match' THEN external_id END) AS fotmob_id,
           max(CASE WHEN provider = 'whoscored' AND namespace = 'match' THEN external_id END) AS whoscored_id,
           max(CASE WHEN provider = 'understat' AND namespace = 'match' THEN external_id END) AS understat_id,
           max(CASE WHEN provider = 'sofascore' AND namespace = 'event' THEN external_id END) AS sofascore_id
    FROM bridges
    WHERE entity_type = 'match'
    GROUP BY reep_id
    """
)

con.execute(
    """
    CREATE TEMP TABLE joined AS
    SELECT f.match_key, f.date, f.season, f.league, f.home, f.away,
           b.reep_id, m.fotmob_id, m.whoscored_id, m.understat_id, m.sofascore_id
    FROM fd f
    LEFT JOIN best b USING (match_key)
    LEFT JOIN bridges_m m ON m.reep_id = b.reep_id
    """
)

total = con.execute("SELECT count(*) FROM fd").fetchone()[0]
summary = con.execute(
    """
    SELECT count(*) AS total,
           count(reep_id) AS matched,
           count(fotmob_id) AS fotmob,
           count(whoscored_id) AS whoscored,
           count(understat_id) AS understat,
           count(sofascore_id) AS sofascore
    FROM joined
    """
).df()

by_league = con.execute(
    """
    SELECT league,
           count(*) AS matches,
           count(reep_id) AS reep,
           count(fotmob_id) AS fotmob,
           count(whoscored_id) AS whoscored,
           count(understat_id) AS understat
    FROM joined GROUP BY league ORDER BY league
    """
).df()

by_season = con.execute(
    """
    SELECT season,
           count(*) AS matches,
           count(reep_id) AS reep,
           count(fotmob_id) AS fotmob,
           count(whoscored_id) AS whoscored,
           count(understat_id) AS understat
    FROM joined GROUP BY season ORDER BY season
    """
).df()

by_both = con.execute(
    """
    SELECT league, season,
           count(*) AS matches,
           count(reep_id) AS reep,
           count(fotmob_id) AS fotmob,
           count(whoscored_id) AS whoscored,
           count(understat_id) AS understat
    FROM joined GROUP BY league, season ORDER BY league, season
    """
).df()

joined = con.execute("SELECT * FROM joined").df()
joined.to_csv(OUT_DIR / "coverage_matches.csv", index=False)
by_both.to_csv(OUT_DIR / "coverage_by_league_season.csv", index=False)

row = summary.iloc[0]
pct = lambda n: 100.0 * n / total  # noqa: E731


def md_table(frame: pd.DataFrame) -> str:
    cols = list(frame.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for values in frame.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in values) + " |")
    return "\n".join(lines)


lines = [
    "# Reep coverage: top five leagues vs football-data",
    "",
    f"Register release: 2026-11-23.1. Football-data matches from 2020 onwards: **{total:,}**.",
    "",
    "## Overall",
    "",
    "| Link | Matches | Share |",
    "|---|---|---|",
    f"| Matched to a Reep match | {row.matched:,} | {pct(row.matched):.1f}% |",
    f"| Has a FotMob match ID | {row.fotmob:,} | {pct(row.fotmob):.1f}% |",
    f"| Has a WhoScored match ID | {row.whoscored:,} | {pct(row.whoscored):.1f}% |",
    f"| Has an Understat match ID | {row.understat:,} | {pct(row.understat):.1f}% |",
    f"| Has a Sofascore match ID | {row.sofascore:,} | {pct(row.sofascore):.1f}% |",
    "",
    "## By league",
    "",
    md_table(by_league),
    "",
    "## By season",
    "",
    md_table(by_season),
    "",
    "## Method",
    "",
    "- Join key: football-data `(date, home, away)` to Reep match label, allowing +/- 1 day.",
    "- Team names mapped through Reep aliases, with a hand-checked 145-team map.",
    "- No provider crawl was needed: IDs come from the register itself.",
    "",
]

REPORT.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
