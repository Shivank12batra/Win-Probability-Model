# Architecture and hosting

## 1. Two separate systems

There is an offline system and an online system. They share code, not runtime.

```
OFFLINE (batch, runs nightly or weekly)
  backfill -> windows table -> train -> calibrate -> evaluate -> model artifact

ONLINE (always on, match days)
  poll feeds -> normalise -> state store -> features -> inference -> API -> UI
```

Training is a batch job. Do not try to run it in the serving path.

---

## 2. Online topology

```
FotMob ─┐
ESPN   ─┼─> collector ─> normaliser ─> Redis (hot state, per match)
        │                      └────> Postgres (event + snapshot history)
        │
        └─> feature builder ─> inference (model artifact) ─> API (SSE)
                                                              │
                                                        Next.js / SvelteKit
```

| Component | Responsibility | Runtime |
|---|---|---|
| **Collector** | Poll fixtures and live matches, respect rate limits, detect schema drift | Always-on worker |
| **Normaliser** | Map team/player names to canonical ids; validate payloads | Worker |
| **State store** | Latest known state per live match | Redis |
| **History** | Snapshots + events for replay and audit | Postgres |
| **Feature builder** | Turn a state into the model feature vector | In-process |
| **Inference** | Load model artifact, produce λ and P(H/D/A) | In-process |
| **API** | `/live`, `/match/{id}`, `/health`, SSE stream | FastAPI |
| **Frontend** | Live chart, match cards | Static or SSR |
| **Monitor** | Data freshness, calibration drift, error rates | Worker |

Latency budget: poll 15 s → normalise <50 ms → features <10 ms → inference <5 ms
→ push <1 s. Total staleness under ~20 s, which is fine for a public product.

---

## 3. Hosting

Constraint: **$0/month**, always-on, no cold starts.

### Recommended: Oracle Cloud Always Free + Cloudflare

```
Cloudflare Pages      -> frontend (free, global CDN)
Oracle Cloud VM       -> Docker Compose:
  (Always Free, ARM)     - api (FastAPI)
                         - collector worker
                         - postgres
                         - redis
                         - caddy
Cloudflare Tunnel     -> TLS + public hostname, no open ports
```

Why: the Always Free ARM instance (4 OCPU / 24 GB) is genuinely free and
genuinely always-on. Everything runs in one place, so there is no cross-service
latency or egress bill. Cloudflare Tunnel avoids exposing the VM.

### Alternative: Fly.io

```
Fly.io  -> api + worker (shared-cpu-1x, ~$3–5/mo)
Neon    -> Postgres (free tier)
Upstash -> Redis (free tier)
Vercel  -> frontend (free)
```

Simpler deploys and better DX, but not free once you need two always-on
processes.

### Avoid

| Option | Why not |
|---|---|
| **Render free web service** | Sleeps after inactivity; a live poller cannot sleep |
| **Vercel serverless for the collector** | No long-running process; cron granularity too coarse |
| **GitHub Actions as the poller** | Minimum 5-minute schedule, unreliable timing |
| **AWS/GCP free tiers** | Time-limited, then billing surprises |

### Model artifacts

Store the trained model in Cloudflare R2 (10 GB free) or as a GitHub release
asset. Load it at API startup and hot-reload on a version bump.

---

## 4. Where to run what

| Job | Best place | Why |
|---|---|---|
| Writing / reviewing code | Cursor / cloud agent / this environment | Fast iteration, PRs, no data transfer |
| Unit tests, linting | CI (GitHub Actions) | Cheap, reproducible |
| Historical backfill (~5 h of requests) | Your machine or the always-on VM | Datacenter IPs are more likely to be blocked; long jobs exceed agent time limits |
| Model training | GitHub Actions or the VM | Batch, CPU-only, minutes not hours |
| Live serving | Always-on VM | No cold starts, persistent connections |
| Frontend | Cloudflare Pages / Vercel | Static, free CDN |

**On Cursor Cloud Agent specifically:** it is a good fit for code changes and
pull requests. It is a poor fit for a multi-hour scrape — sandboxes are
ephemeral, outbound IPs are shared (higher block risk), and long-running jobs hit
time limits. Write and review code there; run the backfill on a machine whose IP
and filesystem persist.

---

## 5. Reliability

The feeds are unofficial, so assume they will break:

1. **Dual source.** FotMob primary, ESPN fallback. Switch automatically on
   repeated failures.
2. **Schema guards.** Validate payload shape before writing. Fail loudly, not
   silently with nulls.
3. **Staleness flag.** Every API response carries `as_of`. The UI shows
   "delayed" if the last update is older than 60 s.
4. **Circuit breaker.** After N consecutive failures, stop retrying and serve
   the last known state with a degraded badge.
5. **Replayable history.** Persist every snapshot so incidents can be
   reconstructed and the model re-scored offline.

---

## 6. Security and secrets

- No credentials are required for the current free stack.
- If licensed APIs are added, keep keys in the VM environment or a secret
  manager — never in the repo.
- Rate-limit the public API; the model is cheap to run but the upstream feeds
  are not.
- Publish a model card: training window, features, calibration results, known
  limitations.
