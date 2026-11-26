# Data sources

**Verified:** 2026-11-26. Every status below was tested live from this machine,
not taken from a tutorial.

The short version: the sources the reference implementation relied on in 2022 are
mostly gone or protected. What is actually available now is better in some ways
(shot-level xG, live momentum) and worse in others (no clean 2010–2020 event
archive).

---

## 1. Status board

| Source | What it gives | Coverage | Access | Verified status |
|---|---|---|---|---|
| **FotMob** (internal JSON) | Fixtures, live clock, score, **live xG**, **shot map with per-shot xG + minute**, momentum, events, lineups | Top 5 + Europe; shot maps from **2020/21** | `fotmob.com/api/data/*` | ✅ 200 |
| **ESPN** (hidden API) | Live score, clock, cards, possession/shots, **shot coordinates** in commentary, pre-match odds | Top 5 + Europe | `site.api.espn.com/apis/site/v2/sports/soccer/*` | ✅ 200 |
| **football-data.co.uk** | Results + closing odds | 1993/94 → 2025/26, top 5 | Static CSVs | ✅ 200 |
| **StatsBomb open data** | Full event streams, 360 data on some matches | 80 competition-seasons; La Liga 2009/10–2020/21, 2015/16 for others | GitHub raw JSON | ✅ 200 |
| **Understat** | Shot-level xG | Top 5 + RPL, 2014– | Scraping | ⚠️ 200 but serving *"We will come back soon"* |
| **WhoScored** | Event data | 2010 → | Scraping | ❌ 403 (Cloudflare) |
| **SofaScore** | Live stats | Broad | Undocumented API | ❌ 403 |
| **ClubElo API** | Elo ratings | Long history | `api.clubelo.com` | ❌ not responding |
| **FBref** | Advanced stats | Historical | Scraping | ⚠️ lost Opta licence Jan 2026; archive only |

---

## 2. The WhoScored reality check

The plan of "WhoScored event data from 2010 to now" is not a free, reliable
path in 2026:

- Direct requests return **403** behind Cloudflare.
- It requires a headless browser, residential proxies, cookie/session handling,
  and constant maintenance. Commercial scraping APIs that can do it cost money
  and carry terms-of-service risk.
- The payoff over the free stack is smaller than it looks: we need **goal
  timing, cards, xG and shot volume**, not every pass. FotMob already provides
  those from 2020/21, and StatsBomb provides full events for 2015/16 plus the
  full La Liga run.

**Recommendation:** do not build the project on WhoScored. Use it only as an
optional enrichment later if you obtain licensed access.

This also means a 2010–2020 archive across all five leagues is not freely
available. That is acceptable: football's goal environment has shifted
(added time, five substitutions, VAR), so 2020→present is arguably the more
relevant training distribution.

---

## 3. Recommended stack

### Training data

| Purpose | Source | Coverage | Why |
|---|---|---|---|
| Elo priors | football-data.co.uk | 1993 → now | Free, complete, includes results and odds |
| Market prior | football-data.co.uk closing odds | 2000s → now | De-vig to implied probabilities |
| In-play training set | FotMob shot maps + events | 2020/21 → now | ~11–12k matches, per-shot xG with minutes |
| Event-depth validation | StatsBomb open data | 2015/16 + La Liga run | Full event streams for richer features |

### Live data

| Purpose | Primary | Fallback |
|---|---|---|
| Fixtures + clock + score | FotMob | ESPN |
| xG + shot map | FotMob | ESPN shot coordinates (own xG model) |
| Cards / subs / events | FotMob | ESPN |
| Pre-match odds | ESPN / football-data | — |

Two independent feeds is the whole reliability strategy. If FotMob changes
shape, ESPN keeps the service up while you fix it.

---

## 4. Rate limits and etiquette

| Source | Suggested interval | Notes |
|---|---|---|
| FotMob | ≥1.5 s between requests, jitter | Poll live matches every 15 s, not every second |
| ESPN | ≥1 s | One scoreboard call covers a whole league |
| football-data | ≤0.5 s | Static files, cache permanently |
| StatsBomb | ≤0.3 s | Download once, store locally |

Rules we follow:

1. Cache everything. Never re-fetch a finished match.
2. Identify with a normal browser user agent; do not disguise traffic.
3. Back off on 429/403; stop on repeated blocks.
4. Do not redistribute raw provider data. Derived probabilities are fine;
   raw feeds are not.
5. Prefer licensed providers if this ever becomes a commercial product.

---

## 5. Backfill plan

| Step | What | Volume | Runtime (est.) |
|---|---|---|---|
| 1 | Results + odds, 1993–2026 | ~50 CSVs | minutes |
| 2 | Elo ratings from results | ~60k matches | seconds |
| 3 | Fixture index, 2020–2026 | ~2,200 dates × 1 call | ~1 hour at 1.5 s |
| 4 | Match details (shots + events) | ~11k matches × 1 call | ~5 hours at 1.5 s |
| 5 | StatsBomb event seasons | ~4,500 matches × 1 file | ~1 hour |
| 6 | Window table build | ~11k × 18 × 2 rows ≈ 400k | minutes |

Run the backfill once, on a machine you control. Commit only code and schemas,
never the data.

---

## 6. Storage layout

```
data/
  raw/
    football_data/{division}_{season}.csv
    fotmob/{match_id}/details.json
    fotmob/{match_id}/shots.csv
    fotmob/{match_id}/events.csv
    statsbomb/{competition}_{season}/{match_id}.json
    espn/{event_id}.json
  processed/
    windows/{match_id}.parquet      # model training rows
    matches.parquet                 # index of usable matches
  elo/
    elo_matches.csv                 # one row per match, pre-match ratings
  live/
    live_{date}.csv                 # snapshots for debugging
```

For the full backfill, move `raw/` to object storage (Cloudflare R2 free tier)
and keep `processed/` in Parquet.
