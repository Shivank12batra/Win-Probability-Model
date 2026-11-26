# Backfill scale test

Matches: **380**. Rows: **14,450** (avg 38.0 per match).

| Check | Result |
|---|---|
| Window targets reconcile with final score | 380/380 |
| First / last window | 0 / 105 minutes |
| Duplicate window rows | 0 |
| Home windows with a red-card advantage | 291 |

Output: `data/processed/windows.parquet`
