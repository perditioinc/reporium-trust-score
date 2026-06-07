"""Local OSS smoke test for the trust-score computation path.

Assumes the local substrate (`make -C local up` / docker compose up) is
already running and reachable at REPORIUM_API_BASE. It:

  1. Runs all three probes (health, synthetic_ask, graph_quality) against the
     local stub -- the same code paths the hourly Action runs in production.
  2. Feeds the probe outputs into lib.score.compute_trust_score -- the real
     composite formula.
  3. Asserts the result is sane for a healthy local substrate:
       - reliability == 1.0   (home 200, api 200, all ask probes completed)
       - quality      > 0.0    (graph-quality read from local Postgres, all
                                families above the KAN-147 floor)
       - 0 < composite <= 100
  4. Prints the snapshot and a single PASS / FAIL line.

Snapshot is written to a temp dir, NOT the repo history/, so the smoke test
never mutates tracked data.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Make the repo root importable (parent of local/).
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Ensure the probes aim at the local stub even if the caller forgot to export.
os.environ.setdefault("REPORIUM_API_BASE", "http://localhost:8080")
os.environ.setdefault("REPORIUM_HOME_URL", "http://localhost:8080/")
os.environ.setdefault("REPORIUM_APP_TOKEN", "local-dev-token")
os.environ.setdefault("REPORIUM_ADMIN_KEY", "local-dev-admin-key")
os.environ.setdefault("REPORIUM_ASK_SLEEP_S", "0")

from lib.score import compute_trust_score  # noqa: E402
from probes import graph_quality, health, synthetic_ask  # noqa: E402


def main() -> int:
    print(f"[smoke] probing local substrate at {os.environ['REPORIUM_API_BASE']}")
    health_out = health.run()
    ask_out = synthetic_ask.run()
    gq_out = graph_quality.run()

    score = compute_trust_score(health_out, ask_out, gq_out)
    now = datetime.now(timezone.utc)
    payload = {
        "score": score,
        "health": health_out,
        "ask": ask_out,
        "graph_quality": gq_out,
        "ts": now.isoformat(),
    }

    # Write the snapshot to a temp dir to prove the storage path works without
    # polluting the tracked history/ tree.
    with tempfile.TemporaryDirectory() as td:
        snap = Path(td) / "smoke_snapshot.json"
        snap.write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"[smoke] wrote snapshot to {snap}")

    print("[smoke] score = " + json.dumps(score, indent=2, sort_keys=True))

    checks = {
        "reliability == 1.0": score["reliability"] == 1.0,
        "quality > 0.0": score["quality"] > 0.0,
        "0 < composite <= 100": 0.0 < score["composite"] <= 100.0,
        "graph-quality available": bool(gq_out.get("available")),
        "graph-quality source is postgres_live": gq_out.get("source") == "postgres_live",
    }
    for name, ok in checks.items():
        print(f"[smoke] check: {name} -> {'ok' if ok else 'FAIL'}")

    if all(checks.values()):
        print(f"[smoke] PASS composite={score['composite']}")
        return 0
    print("[smoke] FAIL one or more checks did not hold")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
