# Roadmap

Each phase has a concrete deliverable and an acceptance test. A phase is done
when the test passes, not when the code is written.

---

## Phase 0 — Foundation ✅ (2026-11-26)

**Deliverable**
- Repository scaffold, packaging, CLI, Makefile.
- Verified data sources (see `docs/DATA_SOURCES.md`).
- Elo builder from football-data.co.uk.
- FotMob / ESPN / StatsBomb ingestion clients.
- Fixed-forward-window training-row builder.

**Acceptance**
- `wpm fd-elo` produces >10k match rows with pre-match ratings.
- `wpm build-windows --id <match>` produces 2 rows per 5-minute window.
- Every source used has a documented licence and status.

**Done:** 12,459 Elo match rows; 36 window rows for a 90-minute match.

---

## Phase 1a — Pre-match prior ✅ (2026-11-26)

**Deliverable**
- Results + closing odds, 2000–2026, five leagues (46,389 matches).
- Running Elo: pre/post rating per match, team timeline, current snapshot.
- De-vigged market probabilities (power method).
- Davidson three-way extension, `nu` fitted pre-2020.
- Walk-forward baseline report.

**Result**
- 11,282 evaluation matches (2020–2026).
- Market RPS **0.1950**, ECE 0.007.
- Elo RPS **0.2036**, ECE 0.035.
- Report: `reports/prior_baseline.md`.

The market beats Elo, as expected. Both are now available as priors/features.

---

## Phase 1b — In-play dataset

**Deliverable**
- Match identity via Reep (no custom registry).
- Full backfill: fixtures 2020→present, then match details (shots + events).
- `matches.parquet` index with a `status` column (`ok`, `missing_shots`, `missing_events`, `abandoned`).
- Window table for every usable match, partitioned by season.
- Data-quality report: coverage by league/season, xG completeness, goal-event consistency.

**Acceptance**
- ≥8,000 matches with usable shot maps.
- ≥95% of matches have goal events consistent with the final score.
- Zero rows violate the leakage rules in `docs/FEATURES.md` §1.4.
- Report committed under `reports/`.

**Risks:** provider gaps in early seasons, abandoned matches, name mismatches.

---

## Phase 2 — Baseline model and backtest

**Deliverable**
- Pre-match baseline: Elo + market prior → W/D/L (no in-play features).
- In-play baseline: Poisson model on state only (time, score, reds, home).
- Full model: state + prior + evidence + interactions.
- Walk-forward evaluation harness: RPS, Brier, log loss, ECE by 15-minute bucket.
- Calibration plots and a model card.

**Acceptance**
- Full model beats the state-only baseline on RPS in the 45–90' buckets.
- ECE < 0.03 overall and < 0.05 in the final 15 minutes.
- At minute 0, probabilities are within ±5 points of the closing market.
- Ablation table in `docs/FEATURES.md` §6 is filled in.

**Risks:** overfitting to one season, weak draw calibration, leakage.

---

## Phase 3 — Live pipeline

**Deliverable**
- Always-on collector for the top five leagues.
- Redis hot state + Postgres snapshot history.
- FastAPI: `/live`, `/match/{id}`, `/health`, SSE stream.
- Staleness flag, dual-feed fallback, circuit breaker.
- Container images and a Compose file.

**Acceptance**
- Live matches appear within 30 s of kickoff.
- Probabilities update within 30 s of a goal.
- Killing the primary feed does not take the service down.
- 72-hour soak test with no process restarts.

---

## Phase 4 — Frontend

**Deliverable**
- Live match list with current probabilities.
- Match page: win-probability timeline, score, xG race, key events.
- Mobile-first layout; shareable match URLs.

**Acceptance**
- First contentful paint < 2 s on 4G.
- Timeline matches the API within one poll interval.
- No layout shift when probabilities update.

---

## Phase 5 — Hardening

**Deliverable**
- Nightly retrain with automatic evaluation gate (do not ship a worse model).
- Drift monitoring: feature distributions, calibration by week.
- Alerting on feed failure and calibration breach.
- Model registry with versions and rollback.

**Acceptance**
- A deliberately broken feed triggers an alert within 5 minutes.
- A model that fails the RPS gate is never promoted.
- Rollback takes under 2 minutes.

---

## Phase 6 — Extensions (after the core is trustworthy)

Candidates, in rough order of value per unit of effort:

1. **Stoppage-time model** — empirical distribution first, ML later.
2. **AGV (Added Goal Value)** — per-player clutch metric from probability deltas.
3. **Leverage index** — rank actions by how much they moved the probability.
4. **Uncertainty bands** — conformal intervals around each probability.
5. **Lineup-adjusted pre-match model** — team sheets ~1 hour before kickoff.
6. **LLM match narrator** — grounded strictly in probability deltas.
7. **Public API + model card** — make the work legible and citable.
