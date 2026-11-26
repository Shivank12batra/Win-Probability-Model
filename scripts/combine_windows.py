"""Combine per-match window CSVs into one parquet and validate at scale."""

from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "data" / "processed" / "windows" / "*.csv"
OUT = ROOT / "data" / "processed" / "windows.parquet"
COVERAGE = ROOT / "data" / "processed" / "reep" / "coverage_matches.csv"
MATCHES = ROOT / "data" / "processed" / "football_data" / "matches.csv"
REPORT = ROOT / "reports" / "backfill_scale_test.md"


def main() -> None:
    con = duckdb.connect()
    con.execute(
        f"CREATE TABLE w AS SELECT * FROM read_csv_auto('{WINDOWS}', union_by_name=true)"
    )
    con.execute(f"COPY w TO '{OUT}' (FORMAT PARQUET)")

    con.execute(
        f"""
        CREATE VIEW finals AS
        SELECT c.fotmob_id, f.home_goals, f.away_goals
        FROM read_csv_auto('{COVERAGE}') c
        JOIN read_csv_auto('{MATCHES}') f
          ON CAST(c.date AS DATE) = CAST(f.date AS DATE)
         AND c.home = f.home AND c.away = f.away AND c.season = f.season
        """
    )

    totals = con.execute(
        """
        SELECT match_id,
               sum(CASE WHEN CAST(is_home AS BOOLEAN) THEN target_goals ELSE 0 END) AS target_home,
               sum(CASE WHEN NOT CAST(is_home AS BOOLEAN) THEN target_goals ELSE 0 END) AS target_away
        FROM w GROUP BY match_id
        """
    ).df()

    check = con.execute(
        """
        SELECT count(*) AS matches,
               sum(CASE WHEN t.target_home = f.home_goals AND t.target_away = f.away_goals THEN 1 ELSE 0 END) AS consistent
        FROM totals t JOIN finals f ON f.fotmob_id = t.match_id
        """
    ).df()

    stats = con.execute(
        """
        SELECT count(*) AS rows,
               count(DISTINCT match_id) AS matches,
               count(*) * 1.0 / count(DISTINCT match_id) AS rows_per_match,
               min(window_start) AS first_window,
               max(window_end) AS last_window,
               sum(CASE WHEN CAST(is_home AS BOOLEAN) AND red_diff <> 0 THEN 1 ELSE 0 END) AS home_red_windows
        FROM w
        """
    ).df()

    duplicates = con.execute(
        """
        SELECT count(*) FROM (
          SELECT match_id, team, window_start, count(*) c
          FROM w GROUP BY 1,2,3 HAVING c > 1
        )
        """
    ).fetchone()[0]

    row = stats.iloc[0]
    lines = [
        "# Backfill scale test",
        "",
        f"Matches: **{int(row.matches):,}**. Rows: **{int(row.rows):,}** "
        f"(avg {row.rows_per_match:.1f} per match).",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Window targets reconcile with final score | {int(check.iloc[0].consistent)}/{int(check.iloc[0].matches)} |",
        f"| First / last window | {int(row.first_window)} / {int(row.last_window)} minutes |",
        f"| Duplicate window rows | {duplicates} |",
        f"| Home windows with a red-card advantage | {int(row.home_red_windows)} |",
        "",
        f"Output: `{OUT.relative_to(ROOT)}`",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
