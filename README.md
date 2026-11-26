# Win Probability Model

Live, in-play win/draw/loss probabilities for the top five European football
leagues — built to be **calibrated**, not just plausible.

The model predicts each team's goal-scoring intensity for the rest of the match
and converts it into outcome probabilities. It is a rebuild of the ASA-inspired
approach in [this article](https://sharmaabhishekk.github.io/projects/win-probability-implementation),
with three structural changes:

1. **Fixed forward windows + Poisson likelihood** instead of regression on a
   shrinking ratio target.
2. **~11k matches** of shot-level xG from 2020/21 onward, not one season.
3. **Walk-forward evaluation** with RPS and ECE by match phase, not visual
   inspection.

## Status

**Phase 0 complete; pre-match prior complete.** Repository, verified sources,
ingestion clients, training-row builder, running Elo, market prior and a
walk-forward baseline comparison are in place. See
[`docs/ROADMAP.md`](docs/ROADMAP.md) and
[`reports/prior_baseline.md`](reports/prior_baseline.md).

## Documentation

| Document | Contents |
|---|---|
| [`docs/FEATURES.md`](docs/FEATURES.md) | Every feature, definition, window, leakage rule, ablation plan |
| [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) | What works in 2026, coverage, rate limits, backfill plan |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Offline vs online systems, hosting, reliability |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phases and acceptance criteria |

## Quickstart

```bash
python3 -m pip install -e .          # or: make install
export PYTHONPATH=src

# Results + odds + running Elo + market prior, 2000-2026 (46k matches)
python3 -m wpm.cli fd-build --start 2000 --end 2026

# Inspect one match: shots, events, live xG
python3 -m wpm.cli fotmob-match --id 4506349

# Build the 5-minute training windows for that match
python3 -m wpm.cli build-windows --id 4506349

# What is live right now
python3 -m wpm.cli fotmob-live
```

## Layout

```
src/wpm/
  config.py            leagues, paths, tuning constants
  ingest/              fotmob, espn, football_data, statsbomb, http
  ratings/elo.py       match-level Elo with pre-match ratings
  features/windows.py  fixed forward-window training rows
  cli.py               command line entry point
docs/                  specification and plans
data/                  gitignored; raw + processed data
```

## Data sources

FotMob (live xG, shot maps), ESPN (fallback, shot coordinates), football-data.co.uk
(results, odds), StatsBomb open data (event depth). See
[`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) for coverage and caveats.

Unofficial feeds are used for a personal/portfolio project with caching and
attribution. Raw provider data is not redistributed. If this becomes a product,
move to a licensed provider.

## Evaluation

Not yet implemented. Planned: walk-forward by season, RPS and Brier, ECE by
15-minute bucket, calibration curves, and a comparison against the closing
market at kickoff.
