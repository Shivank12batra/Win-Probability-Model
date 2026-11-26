# Feature availability: does FotMob suffice?

**Short answer: yes for v1, partly for v2, no for v3.**

FotMob covers every state, shot and xG feature in the v1 plan. It does not
provide event-level tactical data (passes, carries, PPDA, xT), and its match
statistics are **whole-match aggregates**, not time series. Anything that must
change minute by minute has to come from the shot map, the event list, or
momentum.

---

## What FotMob actually returns

| Block | Contents | Granularity |
|---|---|---|
| `shotmap.shots` | x, y, xG, xGOT, body part, situation, minute, team, player, blocked/saved | **per shot** |
| `matchFacts.events` | Goal, Card (yellow/red), Substitution, AddedTime, Half | **per event** |
| `momentum.main.data` | Provider momentum score | **per minute** (2023+) |
| `stats` | Possession, shots, SOT, big chances, passes, corners, tackles, duels, xG splits | **match aggregate only** |
| `lineup` | Starters, subs, formation, team rating, unavailable players, market value | static |
| `playerStats` | Per-player aggregate stats and shot maps | match aggregate |
| `table`, `h2h`, `weather` | Context | static |

Critical detail: `stats.Periods` only contains `"All"`. There is no first-half,
second-half or per-minute split. So possession at minute 60 cannot be recovered
historically.

---

## Coverage by season (spot-checked)

| Data | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|
| Shot map + xG | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Goals / cards / subs | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Lineup + formation + unavailable | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Momentum per minute | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Starter market value | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

This is one match per season, so treat it as indicative. The important point is
that **not every feature is available for every season**.

Also: `content.lineup` can be `false` for some matches. Parsing must handle that.

---

## Feature matrix

Legend: ✅ available · 🟡 derivable · ⚠️ aggregate only (unusable as a
time-varying training feature) · ❌ not available

### G1 — Match state

| Feature | Status | Source |
|---|---|---|
| `minute` | ✅ | live clock / event times |
| `period` | ✅ | Half events |
| `score_diff` | ✅ | Goal events |
| `total_goals` | ✅ | Goal events |
| `is_home` | ✅ | event/team ids |
| `time_since_last_goal` | ✅ | Goal events |
| `half_time_score_diff` | ✅ | events up to Half |
| `effective_minutes_left` | 🟡 | AddedTime events at 45/90; live estimate |

### G2 — Personnel and discipline

| Feature | Status | Source |
|---|---|---|
| `red_diff` | ✅ | Card events (`Red`) |
| `red_minutes_elapsed` | ✅ | Card events |
| `subs_made_diff` | ✅ | Substitution events |
| `yellow_diff` | ✅ | Card events (`Yellow`) |

### G3 — Pre-match strength

| Feature | Status | Source |
|---|---|---|
| `elo_diff`, `elo_*` | ❌ | football-data (external) |
| `elo_uncertainty` | ❌ | football-data (external) |
| `market_p_*` | ❌ | football-data / ESPN (external) |
| `xg_attack`, `xg_defence` | ✅ | derived from historical shot maps |
| `matches_played_season` | ✅ | fixture dates |
| `promoted` | 🟡 | no prior top-five season |
| `lineup_strength` | 🟡 | starters, formation, team rating; market value only 2025+ |
| `injuries_suspensions` | 🟡 | `lineup.*.unavailable` (type, expected return); 2020+ |

### G4 — In-match evidence

| Feature | Status | Source |
|---|---|---|
| `xg_for`, `xg_against`, `xg_diff` | ✅ | shot map |
| `xg_window` (last 10 min) | ✅ | shot map |
| `shots_for`, `shots_against` | ✅ | shot map |
| `shots_on_target` | ✅ | `isOnTarget` |
| `xg_overperformance` | ✅ | goals − xG |
| `xg_on_target` (xGOT) | ✅ | shot map |
| `big_chances` | 🟡 | derive from xG threshold, or aggregate stat |
| `momentum_10` | ⚠️ | per minute, but only 2023+ |
| `possession` | ⚠️ | aggregate only |
| `passes`, `accurate_passes` | ⚠️ | aggregate only |
| `corners` | ⚠️ | aggregate only, no event times |
| `duels`, `tackles`, `interceptions` | ⚠️ | aggregate only |
| `final_third_entries` | ❌ | no per-minute event stream |
| `ppda` | ❌ | no event stream |
| `progressive_passes`, `carries` | ❌ | no event stream |
| `xt`, `vaep`, `g+` | ❌ | require full events |

### G5 — Context

| Feature | Status | Source |
|---|---|---|
| `league_id` | ✅ | `general.leagueName` |
| `season_phase` | ✅ | date |
| `rest_days` | ❌ | football-data fixtures |
| `match_importance` | 🟡 | table / market prior |

### G6 — Interactions

All derived from the above; no new data needed.

---

## What this means for the model

**v1 is fully covered by FotMob.** Time, score, red cards, substitutions, xG,
shots, SOT, xGOT and windowed xG are all per-event or per-shot, available from
2020/21. Add Elo and market odds from football-data and the v1 feature set is
complete.

**Do not build v1 on aggregate stats.** Possession, passes, corners and duels
are only available as final match totals. Using them in a minute-60 snapshot
would leak the rest of the match. They are useful for post-match analysis, not
for in-play training.

**Momentum is a trap for v1.** It only exists from 2023, and it is a proprietary
black box. Our own `xg_window` is reproducible and available across the whole
training window. Keep momentum as a Tier 3 ablation, not a core feature.

**Lineups are better than expected.** FotMob exposes starters, formation, team
rating, and an `unavailable` list with injury type and expected return. That
makes lineup strength and availability a realistic v2 feature without new
sources.

**WhoScored is only needed for the tactical tier.** PPDA, progressive passes,
carries, xT/VAEP and per-minute possession require a full event stream. Those
are v3, not blockers.

---

## Verdict

| Tier | Needs | FotMob enough? |
|---|---|---|
| v1 state + shots + xG + prior | Goals, cards, subs, shot maps, Elo, odds | **Yes** |
| v2 lineup and availability | Starters, formation, unavailable | **Mostly** (market value only 2025+) |
| v3 tactical event features | Passes, carries, PPDA, xT | **No** — needs WhoScored/StatsBomb/Scoresway |
