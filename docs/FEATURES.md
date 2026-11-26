# Feature specification

**Status:** draft v0.1 · **Last updated:** 2026-11-26
**Scope:** in-play win/draw/loss probabilities, top five European leagues.

This document is the single source of truth for what the model sees. Every
feature is listed with its definition, computation window, availability, and
whether it has earned its place yet. Nothing enters the production model
without passing the ablation protocol in §6.

---

## 1. Modelling contract

### 1.1 Target

We do **not** predict win/draw/loss directly. We predict how many goals each
team will score in a **fixed forward window**:

```
for every match, for every 5-minute window w:
    features  = state at the start of w   (only information available then)
    target    = goals scored by the team during w
```

The window is fixed so the target has the same scale at minute 3 and minute 87.
This is the key difference from the reference implementation, which used
`goals remaining ÷ intervals remaining` — a target whose scale shrinks as the
match progresses.

- One row per `(match, window, team)`.
- Two rows per window (home perspective, away perspective).
- Non-overlapping windows for training; sliding windows at inference.

### 1.2 Likelihood

Goals in a window are a small non-negative count, so the model is trained with a
**Poisson likelihood**:

```
loss = λ − y · log(λ)
```

where `λ` is the expected goals in the window. This guarantees non-negative
intensities and matches the variance structure of count data. Squared error
(the reference implementation's choice) does neither.

### 1.3 From intensities to outcomes

At live minute *t*:

```
λ_remaining = λ_window × (effective_minutes_left / window_minutes)
```

`effective_minutes_left` includes the stoppage-time estimate (§4.6). Home and
away remaining goals are then treated as Poisson variables and combined:

```
P(home win) = Σ_{h > a} P_H(h) · P_A(a)
P(draw)     = Σ_k        P_H(k) · P_A(k)
```

Exact, microseconds, no Monte Carlo. Simulation is used only to propagate
uncertainty in stoppage time and strength estimates.

### 1.4 Leakage rules

These are non-negotiable and are enforced in code review:

1. A feature at window *w* may only use events with `time <= w.start`.
2. Never use full-match aggregates (final xG, final shots, final momentum).
3. `time_interval` is excluded from features. The reference implementation found
   it leaked the target; we reproduce that decision.
4. Pre-match odds must be **closing** odds, captured before kickoff.
5. Cross-validation is grouped by match. No match appears in both train and
   validation.
6. Trailing-window features are computed backwards from `w.start`, never forward.

---

## 2. The reference implementation's features

From the source article (ASA methodology, 2017/18 Premier League):

| Feature | What it encodes | Decision | Notes |
|---|---|---|---|
| `score_differential` | Signed margin | **Keep** | Core state variable |
| `goals_scored` | Total goals so far | **Keep** | Proxies how open the game is |
| `player_differential` | Red-card-adjusted man advantage | **Keep, extend** | Add red-card timing |
| `own_yellow_cards` | Team's bookings | **Drop from v1** | Weak signal for goals; keep for stoppage-time model |
| `opposition_yellow_cards` | Opponent bookings | **Drop from v1** | Same |
| `is_home_team` | Home/away | **Keep** | Interacts with state |
| `avg_team_xt` | Rolling 4-match xT (strength) | **Replace** | Use Elo + xG ratings |
| `avg_opp_xt` | Rolling 4-match opponent xT | **Replace** | Same |
| `minutes_remaining` | Time left | **Keep** | Must include stoppage time |
| `time_interval` | 100-frame position | **Exclude** | Leakage, per author |
| `time_intervals_remaining` | Frames left | **Keep as exposure** | Not a model feature — used to scale λ |
| `running_xt_differential` | Cumulative in-match xT diff | **Replace** | Use xG diff + windowed xG |

The reference work used xT for team strength only because Elo was unavailable.
That is the weakest part of its setup and the easiest to improve.

---

## 3. Feature groups

### G1 — Match state

| Feature | Definition | Window | Tier |
|---|---|---|---|
| `minute` | Elapsed match minute at window start | point | 1 |
| `period` | 1 or 2 | point | 1 |
| `score_diff` | Team goals − opponent goals | cumulative | 1 |
| `total_goals` | Goals in the match so far | cumulative | 1 |
| `is_home` | 1 if team is home | static | 1 |
| `time_since_last_goal` | Minutes since the most recent goal by either side | point | 2 |
| `half_time_score_diff` | Margin at half-time (null in first half) | point | 2 |
| `effective_minutes_left` | `(90 − minute) + expected_added_time` | point | 1 |

`effective_minutes_left` is an **exposure offset**, not a learned feature. It
scales the window rate into a remaining-match rate.

### G2 — Personnel and discipline

| Feature | Definition | Window | Tier |
|---|---|---|---|
| `red_diff` | Red cards for − against | cumulative | 1 |
| `red_minutes_elapsed` | Minutes since each red card, min over team | point | 2 |
| `subs_made_diff` | Substitutions used, for − against | cumulative | 2 |
| `yellow_diff` | Yellows for − against | cumulative | 3 |

### G3 — Pre-match strength (the prior)

| Feature | Definition | Window | Tier |
|---|---|---|---|
| `elo_diff` | `elo_home + home_advantage − elo_away` | pre-match | 1 |
| `elo_home`, `elo_away` | Raw ratings | pre-match | 1 |
| `elo_uncertainty` | Rating deviation or `1/sqrt(matches_played)` | pre-match | 2 |
| `market_p_home/draw/away` | Implied probabilities from closing odds, de-vigged | pre-match | 1 |
| `xg_attack`, `xg_defence` | Opponent-adjusted rolling xG ratings | pre-match | 2 |
| `matches_played_season` | Reliability of the strength estimate | pre-match | 2 |
| `promoted` | No top-five history this season | pre-match | 3 |

#### Running Elo, not a season-end dump

A season-end rating is unusable for live prediction: using it to score an
October match leaks the future. Elo is therefore produced as a **time series**,
and only the value as of kickoff is exposed to the model.

| Artefact | Granularity | Use |
|---|---|---|
| `elo_matches.csv` | one row per match | `elo_home_pre` / `elo_away_pre` (model input), post ratings for audit |
| `elo_timeline.csv` | one row per team per match | rating evolution, charts, debugging |
| `elo_current.csv` | latest snapshot | serving fallback, cold starts |

The pre-match rating of match *N* is exactly the post-match rating of that
team's previous match (tested). The three-way extension uses Davidson's draw
model, with `nu` fitted only on seasons before the evaluation window
(0.755 on 2000–2019).

### G4 — In-match evidence

| Feature | Definition | Window | Tier |
|---|---|---|---|
| `xg_for`, `xg_against` | Cumulative xG | cumulative | 1 |
| `xg_diff` | `xg_for − xg_against` | cumulative | 1 |
| `xg_window` | xG in the trailing 10 minutes | trailing 10 | 1 |
| `shots_for`, `shots_against` | Cumulative shot counts | cumulative | 1 |
| `xg_overperformance` | `goals − xG` | cumulative | 2 |
| `momentum_10` | Provider momentum score, trailing 10 | trailing 10 | 3 |
| `final_third_entries` | Attacking-third entries | cumulative | 3 |

xG already contains shot *quality*; shot counts add *volume*, which xG discards.
Both are kept pending ablation.

### G5 — Context

| Feature | Definition | Tier |
|---|---|---|
| `league_id` | Categorical league effect | 1 |
| `season_phase` | Early / mid / late season | 3 |
| `rest_days` | Days since last competitive match | 3 (deferred) |
| `match_importance` | Table stakes at kickoff | 3 (deferred) |

### G6 — Engineered interactions

These are expected to matter more than most raw features:

| Feature | Rationale |
|---|---|
| `score_diff × effective_minutes_left` | The value of a lead grows non-linearly with time |
| `elo_diff × fraction_elapsed` | Strength matters early, fades as evidence accumulates |
| `red_diff × effective_minutes_left` | A red card matters more the longer it is played with |
| `xg_diff × fraction_elapsed` | In-match evidence should dominate late |
| `is_home × score_diff` | Home teams behave differently when leading/trailing |

After per-phase models, these interactions are the cheapest way to approximate
the time-varying coefficients used in the published Bayesian approach.

---

## 4. Availability and timing

| Feature group | Historical (training) | Live (inference) | Source |
|---|---|---|---|
| G1 state | ✅ from event feed | ✅ | FotMob / ESPN |
| G2 personnel | ✅ | ✅ | FotMob events |
| G3 prior | ✅ | ✅ (pre-kickoff) | football-data, Elo |
| G4 evidence | ✅ | ✅ | FotMob shot map / ESPN |
| G5 context | ✅ | ✅ | fixtures |
| G6 interactions | derived | derived | — |

Historical in-play data starts in **2020/21** for FotMob shot maps. Elo priors
can use results back to the 1990s.

---

## 5. Deliberately excluded

| Feature | Why excluded |
|---|---|
| Possession % | Mostly a consequence of the scoreline, not a cause |
| Yellow cards as strength | Weak proxy; kept only for stoppage time |
| Injury news | Unreliable, late, and expensive to maintain |
| Weather, crowd, referee (for goals) | Small effects, large state-space cost |
| Bench strength | Requires player ratings plus reliable lineups; v3 at best |
| `time_interval` | Leakage (confirmed by the reference author) |

Adding features is not free: each one fragments the state space and makes
calibration harder. The published Bayesian model deliberately keeps its feature
set compact for this reason.

---

## 6. Ablation protocol

Every group is a hypothesis, not a decision. Evaluate with walk-forward seasons
and group by match.

| ID | Group removed | Question | Decision rule |
|---|---|---|---|
| A1 | G3 Elo | Does Elo improve calibration early in matches? | Keep if ΔRPS < 0 and ΔECE < 0 for the 0–30' bucket |
| A2 | G3 market prior | Is the market prior additive to Elo? | Keep if it improves RPS without worsening ECE |
| A3 | G4 xG | Does in-match xG beat shots alone? | Keep the better of the two |
| A4 | G4 shots | Do shot counts add volume beyond xG? | Keep if ΔRPS < 0 |
| A5 | G4 windowed xG | Does momentum add beyond cumulative xG? | Keep if ΔRPS < 0 in the 45–75' bucket |
| A6 | G2 red timing | Does timing beat a simple count? | Keep if ΔECE < 0 |
| A7 | G6 interactions | Do interactions beat raw features? | Required: if not, revisit the model form |
| A8 | G2 yellows | Do yellows help at all? | Drop unless ΔRPS < 0 |

Metrics are always reported **by match phase**: 0–15, 15–30, 30–45, 45–60,
60–75, 75–90, 90+. A global average hides the only regime that matters.

---

## 7. Open questions

1. Should the model be one global model, or per-league with partial pooling?
2. Is a 5-minute window the right granularity, or 10 minutes for stability?
3. Does a Dixon-Coles correction materially improve draw calibration?
4. Does per-phase modelling beat interaction features?
5. How much does the stoppage-time estimate improve late-game ECE?
