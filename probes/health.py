"""Reliability probe: hit Reporium home page and API /health, record status + TTFB."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import requests

# Defaults point at the live production system (unchanged behavior). The
# REPORIUM_HOME_URL / REPORIUM_API_BASE overrides let the local OSS smoke
# harness (see local/) aim the probe at a contract stub instead. See
# local/README.md for the env-pointing rationale.
HOME_URL = os.environ.get("REPORIUM_HOME_URL", "https://www.reporium.com/")
_API_BASE = os.environ.get(
    "REPORIUM_API_BASE", "https://reporium-api-573778300586.us-central1.run.app"
).rstrip("/")
API_HEALTH_URL = f"{_API_BASE}/health"
TIMEOUT = 10


def _probe(url: str) -> tuple[int, int]:
    """Return (status_code, ttfb_ms). On failure returns (0, -1)."""
    try:
        start = time.perf_counter()
        resp = requests.get(url, timeout=TIMEOUT, stream=True)
        # Reading one byte forces TTFB measurement.
        _ = next(resp.iter_content(1), b"")
        ttfb_ms = int((time.perf_counter() - start) * 1000)
        status = resp.status_code
        resp.close()
        return status, ttfb_ms
    except Exception:
        return 0, -1


def run() -> dict:
    home_status, home_ttfb_ms = _probe(HOME_URL)
    api_status, api_ttfb_ms = _probe(API_HEALTH_URL)
    return {
        "home_status": home_status,
        "home_ttfb_ms": home_ttfb_ms,
        "api_health_status": api_status,
        "api_health_ttfb_ms": api_ttfb_ms,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    print(json.dumps(run()))
