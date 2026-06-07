"""Graph-quality probe: pull /metrics/graph-quality so the Quality sub-score
can react to KAN-147 invariant violations (precision_proxy floor, dead edge
families).

KAN-174: hourly probe was returning composite=1.0 even when graph regressions
were firing because Quality was hard-coded to 1.0. This probe surfaces the
edge-type metrics so `lib.score.quality_subscore` can weight them by
edge-count x precision and hard-fail when any family drops below the floor.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests

# Default points at the live production API (unchanged behavior). The
# REPORIUM_API_BASE override lets the local OSS smoke harness (see local/)
# aim the probe at a contract stub backed by a local Postgres. See
# local/README.md.
_API_BASE = os.environ.get(
    "REPORIUM_API_BASE", "https://reporium-api-573778300586.us-central1.run.app"
).rstrip("/")
GRAPH_QUALITY_URL = f"{_API_BASE}/metrics/graph-quality"
TIMEOUT = 30


def run() -> dict:
    """Return the raw graph-quality payload, or an error envelope."""
    ts = datetime.now(timezone.utc).isoformat()
    admin_key = os.environ.get("REPORIUM_ADMIN_KEY", "")
    if not admin_key:
        return {
            "ts": ts,
            "available": False,
            "error": "REPORIUM_ADMIN_KEY not set; skipping",
        }
    try:
        resp = requests.get(
            GRAPH_QUALITY_URL,
            headers={"X-Admin-Key": admin_key, "Accept": "application/json"},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return {
                "ts": ts,
                "available": False,
                "error": f"HTTP {resp.status_code}",
            }
        body = resp.json()
        body["ts"] = ts
        return body
    except Exception as exc:  # noqa: BLE001 - tolerate all network failures
        return {"ts": ts, "available": False, "error": str(exc)}


if __name__ == "__main__":
    print(json.dumps(run()))
