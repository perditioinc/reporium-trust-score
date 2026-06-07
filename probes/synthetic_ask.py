"""Synthetic ask probe: stream 3 canary queries through /intelligence/ask/stream."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import requests

# Default points at the live production API (unchanged behavior). The
# REPORIUM_API_BASE override lets the local OSS smoke harness (see local/)
# aim the probe at a contract stub. See local/README.md.
_API_BASE = os.environ.get(
    "REPORIUM_API_BASE", "https://reporium-api-573778300586.us-central1.run.app"
).rstrip("/")
ASK_URL = f"{_API_BASE}/intelligence/ask/stream"
TIMEOUT = 60
# Inter-query courtesy sleep against the live API. Overridable (default 15s
# unchanged) so the local OSS smoke harness can set it to 0. See local/.
RATE_LIMIT_SLEEP_S = float(os.environ.get("REPORIUM_ASK_SLEEP_S", "15"))

CANARY_QUERIES = [
    "what is a vector database",
    "react alternatives for state management",
    "python web framework for async apps",
]


def _parse_sse_line(line: bytes) -> dict | None:
    """Parse a single SSE `data: {...}` line into a dict. Return None if not JSON data."""
    if not line:
        return None
    text = line.decode("utf-8", errors="replace").strip()
    if not text.startswith("data:"):
        return None
    payload = text[len("data:"):].strip()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def probe_query(question: str, token: str) -> dict:
    """Run one query and return timing + completion info."""
    result: dict = {"probe": question, "completed": False}
    try:
        start = time.perf_counter()
        resp = requests.post(
            ASK_URL,
            json={"question": question},
            headers={
                "X-App-Token": token,
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
            },
            stream=True,
            timeout=TIMEOUT,
        )
        result["http_status"] = resp.status_code
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            resp.close()
            return result

        ttfb_ms = None
        sources_ms = None
        first_token_ms = None
        done_ms = None
        source_count = 0

        for raw_line in resp.iter_lines():
            if ttfb_ms is None:
                ttfb_ms = int((time.perf_counter() - start) * 1000)
            event = _parse_sse_line(raw_line)
            if event is None:
                continue
            etype = event.get("type")
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            if etype == "sources" and sources_ms is None:
                sources_ms = elapsed_ms
                src = event.get("sources") or event.get("data") or []
                if isinstance(src, list):
                    source_count = len(src)
                elif isinstance(src, dict):
                    source_count = len(src.get("sources") or [])
            elif etype == "token" and first_token_ms is None:
                first_token_ms = elapsed_ms
            elif etype == "done":
                done_ms = elapsed_ms
                result["completed"] = True
                break
            elif etype == "error":
                result["error"] = event.get("message") or "stream error"
                break

        resp.close()
        result["ttfb_ms"] = ttfb_ms
        result["sources_ms"] = sources_ms
        result["first_token_ms"] = first_token_ms
        result["total_ms"] = done_ms
        result["source_count"] = source_count
    except Exception as exc:  # noqa: BLE001 - tolerate all network failures
        result["error"] = str(exc)
        result["completed"] = False
    return result


def run() -> dict:
    token = os.environ.get("REPORIUM_APP_TOKEN", "")
    probes = []
    if not token:
        for q in CANARY_QUERIES:
            probes.append({
                "probe": q,
                "error": "REPORIUM_APP_TOKEN not set; skipping",
                "completed": False,
            })
        return {"probes": probes, "ts": datetime.now(timezone.utc).isoformat()}

    for i, q in enumerate(CANARY_QUERIES):
        probes.append(probe_query(q, token))
        if i < len(CANARY_QUERIES) - 1:
            time.sleep(RATE_LIMIT_SLEEP_S)

    return {"probes": probes, "ts": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    print(json.dumps(run()))
