# Reep: the match identity layer

**Decision: use Reep as the match key. Do not build a custom canonical registry.**

Reep (`withqwerty/reep`, live at [reep.football](https://reep.football)) is a
CC0 cross-provider register. It maps players, teams, competitions, seasons and —
critically for us — **matches** across providers.

Register release tested: `2026-11-23.1`.

---

## Why this matters

Every provider invents its own match ID. Without a crosswalk, joining FotMob to
WhoScored to football-data means fuzzy-matching team names and dates for every
provider pair. Reep already does that work: 1,496,974 match entities, each with
provider IDs attached.

We store `reep_id` on every match and hang the provider IDs off it.

---

## Measured coverage

Football-data spine, seasons 2020–2026, top five leagues: **11,282 matches**.

| Link | Matches | Share |
|---|---|---|
| Matched to a Reep match | 11,281 | 100.0% |
| Has a FotMob match ID | 11,239 | 99.6% |
| Has a WhoScored match ID | 10,983 | 97.3% |
| Has a Sofascore match ID | 10,980 | 97.3% |
| Has an Understat match ID | 493 | **4.4%** |

By league:

| League | Matches | Reep | FotMob | WhoScored | Understat |
|---|---|---|---|---|---|
| Bundesliga | 1,926 | 1,926 | 1,918 | 1,872 | 0 |
| Premier League | 2,390 | 2,390 | 2,390 | 2,330 | 493 |
| La Liga | 2,409 | 2,409 | 2,397 | 2,349 | 0 |
| Ligue 1 | 2,157 | 2,157 | 2,147 | 2,103 | 0 |
| Serie A | 2,400 | 2,399 | 2,387 | 2,329 | 0 |

---

## What this tells us

1. **The registry problem is solved.** 99.6% of our matches have a FotMob ID and
   97.3% have a WhoScored ID. We can pull shot maps and event data by ID instead
   of matching names.
2. **Understat is not a backbone.** It covers 4.4% of matches, all in the
   Premier League, and the site is currently offline. Use it as optional
   enrichment only.
3. **The 2026 season is incomplete in Reep.** Of 548 current-season matches,
   FotMob bridges cover 92.5% and WhoScored 45.6%. That lag does not affect the
   live product: the live collector receives the provider match ID directly, and
   only needs Reep for historical joins.
4. **One match is unmatched** (Fiorentina v Atalanta, 2026-05-22), almost
   certainly a rearranged fixture. That is an override, not a system.

---

## Method

- Parse Reep match labels: `Home v Away, YYYY-MM-DD`.
- Map football-data team names to Reep canonical names via Reep aliases, with a
  hand-checked 145-team map (`config/team_map.csv`).
- Join on `(date ± 1 day, home, away)`.
- Attach provider IDs from the `bridges` table.

Football-data is the spine because it has every result and closing odds.
Reep supplies identity. FotMob/WhoScored supply shots and events.

---

## Reproducing

```bash
# 1. download the register (~307 MB, CC0)
curl -L https://reep.football/downloads/duckdb \
  -o data/raw/reep/reep-register.duckdb

# 2. rebuild the team map (writes config/team_map.csv)
python3 scripts/explore_reep_teams.py

# 3. rebuild the coverage report
python3 scripts/reep_coverage.py
```

Outputs:

- `reports/reep_coverage.md`
- `data/processed/reep/coverage_matches.csv` (per-match provider IDs)
- `config/team_map.csv` (curated, committed)

---

## Caveats

- Reep maps IDs, not data. It carries no score, no xG, no events.
- Coverage is added competition by competition; check the report after each
  release.
- Provider IDs can be missing for very recent matches. The live path should not
  depend on Reep.
- Reep IDs are stable but redirects exist; resolve `redirects` before storing a
  merged ID.
