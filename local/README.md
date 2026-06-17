# Local OSS dev substrate

A $0, fully self-hosted stand-in for every Reporium cloud dependency the
hourly trust probes consume, so you can exercise the trust-score computation
path end to end with no cloud, no secrets, and no paid model.

This directory is **additive and local only**. It never points at production,
and nothing here runs in CI. The production probes keep their live URLs as
defaults; the substrate works by setting environment overrides.

## What the trust score depends on (and the OSS substitute)

| Production dependency | Consumed by | OSS substitute here |
| --- | --- | --- |
| `https://www.reporium.com/` home page (expects 200) | `probes/health.py` | `stub` `/` returns 200 HTML |
| Cloud Run `reporium-api` `/health` (expects 200) | `probes/health.py` | `stub` `/health` returns 200 JSON |
| `reporium-api` `/intelligence/ask/stream` SSE, LLM-backed, `X-App-Token` auth | `probes/synthetic_ask.py` | `stub` emits a deterministic canned `sources` -> `token` -> `done` stream (no paid model) |
| `reporium-api` `/metrics/graph-quality` JSON, Postgres-backed, `X-Admin-Key` auth | `probes/graph_quality.py` | `stub` reads edge-family metrics **live from a local Postgres** seeded from `seed/graph_quality.sql`, shaping the same `source: "postgres_live"` contract |

The datastore behind graph-quality is a real Postgres container (`postgres:16-alpine`),
so the most data-shaped part of the score is exercised against an actual SQL
query, not a hard-coded blob. The remaining endpoints (home, health, ask) are
deterministic stubs.

## How the probes are pointed locally

The three probes default to the live production URLs (unchanged behavior). The
only wiring added is environment-variable overrides:

- `REPORIUM_API_BASE` -> base URL for `/health`, `/intelligence/ask/stream`,
  `/metrics/graph-quality`
- `REPORIUM_HOME_URL` -> home-page reliability target
- `REPORIUM_ASK_SLEEP_S` -> inter-query courtesy sleep (default 15s; set 0 locally)

`REPORIUM_APP_TOKEN` / `REPORIUM_ADMIN_KEY` already existed; the stub accepts
any non-empty value (it checks only that a header is present), so **no real
secret is ever needed locally**.

See `.env.example` for the full set.

## Quick start

```bash
# from the repo root
make up      # build + start stub + postgres, wait until healthy
make smoke   # run the three probes against the stub + compute a trust score
make down    # stop and remove containers + volumes
```

Or directly inside `local/`:

```bash
docker compose up -d --build --wait
python smoke.py
docker compose down -v
```

`smoke.py` asserts a healthy substrate yields `reliability == 1.0`,
`quality > 0`, `0 < composite <= 100`, and that graph-quality came back
`available` with `source: "postgres_live"`. It writes its snapshot to a temp
dir, so it never mutates the tracked `history/` tree.

## Tuning the score for testing

Edit `seed/graph_quality.sql` to drive regressions through the same code path
the production probe uses. For example, drop `EXTENDS.precision_proxy` below
`0.7` and re-run `make seed && make smoke` to watch the Quality sub-score
hard-fail to 0 (and the composite fall to 65), exactly as KAN-174 intends.
