# reporium-trust-score

![Trust Score](https://img.shields.io/badge/trust-pending-lightgrey)

Single source of truth for Reporium trust metrics. Hourly probes measure
reliability, quality, integrity, and freshness of the live system and commit
the result as a JSON snapshot to this repo — a free, tamper-evident audit trail.

## Composite formula

```
composite = 30*reliability + 35*quality + 20*integrity + 15*freshness
```

All four terms are normalized to `[0, 1]` before weighting, so a perfect score
is `100.0`.

**Phase 1 status:** only `reliability` is measured. `quality`, `integrity`, and
`freshness` are hard-coded to `1.0` as placeholders and come online in later
phases (see roadmap).

`reliability` currently folds together:

- Home page (`https://www.reporium.com/`) returns 200
- API health (`/health`) returns 200
- Synthetic `ask/stream` probes complete cleanly (`{type: "done"}` received)

## How it runs

- GitHub Action `hourly.yml` triggers on `cron: '0 * * * *'` (and `workflow_dispatch`)
- Runs the two probes in `probes/`
- Computes the composite via `lib/score.py`
- Writes `history/YYYY/MM/DD/HH.json` via `lib/storage.py`
- `github-actions[bot]` commits and pushes that file

## Where data lives

Every hourly snapshot is a JSON file committed to `history/` in this repo.
Public, diffable, time-stamped. No database, no blob store — the git log *is*
the audit trail.

## Secret required

The synthetic-ask probe needs an app token. Kim must set it once:

```bash
gh secret set REPORIUM_APP_TOKEN \
  --body "<token>" \
  --repo perditioinc/reporium-trust-score
```

If unset, `probes/synthetic_ask.py` skips gracefully (each probe records
`"error": "REPORIUM_APP_TOKEN not set; skipping"`) and `reliability` drops to 0
until it's configured. **Never commit the token value.**

## Roadmap

See [`CONFLUENCE_REPORIUM_TRUST_ROADMAP.md`](../CONFLUENCE_REPORIUM_TRUST_ROADMAP.md)
in the main platform directory. This repo is the Phase 1 scaffold. Phases 2–10
bring the Quality, Integrity, and Freshness terms online.

## Local smoke test

```bash
pip install -r requirements.txt
python -m probes.health          # prints JSON to stdout
python -m probes.synthetic_ask   # needs REPORIUM_APP_TOKEN in env
```

## License

MIT — see [`LICENSE`](LICENSE).
