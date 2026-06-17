"""Local OSS contract stub for the Reporium trust-score probes.

This is a $0, dependency-light stand-in for the live Reporium cloud surface
that the hourly trust probes consume. It serves the exact contracts the three
probes read, so the trust-score computation path can be exercised end to end
with no cloud, no secrets, and no paid model.

Endpoints served (mirroring the production contract the probes expect):

  GET  /                          -> 200 text/html  (home-page reliability probe)
  GET  /health                    -> 200 application/json (API health probe)
  POST /intelligence/ask/stream   -> 200 text/event-stream SSE: emits
                                     `sources`, `token`, then `done` -- the
                                     synthetic-ask probe records `completed`
                                     when it sees `{type: "done"}`.
                                     Requires header X-App-Token (any value).
  GET  /metrics/graph-quality     -> 200 application/json edge-family metrics,
                                     read LIVE from the local Postgres so the
                                     payload mirrors production's
                                     `source: "postgres_live"`. Requires
                                     header X-Admin-Key (any value).

Cloud -> OSS substitution map:
  Cloud Run reporium-api          -> this stdlib http.server stub
  reporium.com home page          -> stub `/`
  Vertex/LLM-backed ask/stream    -> deterministic canned SSE (no paid model)
  Postgres-backed graph-quality   -> local Postgres container (real psql query)

Only the Python stdlib is used for the HTTP server. The single non-stdlib
dependency is `psycopg2-binary` for reading the local Postgres; if it is
absent or the database is unreachable the stub falls back to a static payload
so the smoke test still proves the compute path (and logs that it did so).
"""
from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "0.0.0.0"
PORT = int(os.environ.get("STUB_PORT", "8080"))

# Canned answers for the synthetic-ask canary queries. Deterministic, no model.
_CANNED_TOKENS = ["This ", "is ", "a ", "local ", "stub ", "answer."]


def _pg_graph_quality() -> dict | None:
    """Read edge-family metrics from the local Postgres. Returns a payload
    dict shaped like production's /metrics/graph-quality, or None on failure."""
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return None
    try:
        import psycopg2  # type: ignore
    except Exception:
        return None
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
    except Exception:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT edge_type, live_edges, precision_proxy, recall_proxy, "
                "eligible_repos, observed_repos, invalid_live_edges "
                "FROM graph_quality_edge_types ORDER BY edge_type"
            )
            rows = cur.fetchall()
        edge_types: dict[str, dict] = {}
        total_edges = 0
        for (et, live, prec, recall, elig, obs, invalid) in rows:
            total_edges += int(live or 0)
            if et == "DEPENDS_ON":
                # DEPENDS_ON exposes exact precision/recall in production.
                edge_types[et] = {
                    "live_edges": int(live or 0),
                    "precision": float(prec) if prec is not None else None,
                    "recall": float(recall) if recall is not None else None,
                }
            else:
                edge_types[et] = {
                    "live_edges": int(live or 0),
                    "eligible_repos": int(elig or 0),
                    "observed_repos": int(obs or 0),
                    "invalid_live_edges": int(invalid or 0),
                    "precision_proxy": float(prec) if prec is not None else None,
                    "recall_proxy": float(recall) if recall is not None else None,
                }
        return {
            "available": True,
            "source": "postgres_live",
            "edge_types": edge_types,
            "summary": {
                "edge_types_present": sorted(edge_types.keys()),
                "total_edges": total_edges,
            },
            "notes": [
                "Local OSS stub: edge-family metrics read live from the local "
                "Postgres seed (see local/seed/graph_quality.sql).",
            ],
        }
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


# Static fallback if Postgres is unavailable. Shaped exactly like the live
# contract; all four families above the KAN-147 floor so the compute path
# yields a healthy, nonzero Quality sub-score.
_STATIC_GRAPH_QUALITY = {
    "available": True,
    "source": "static_fallback",
    "edge_types": {
        "DEPENDS_ON": {"live_edges": 250, "precision": 1.0, "recall": 1.0},
        "ALTERNATIVE_TO": {"live_edges": 120, "precision_proxy": 0.95, "recall_proxy": 1.0},
        "EXTENDS": {"live_edges": 40, "precision_proxy": 0.9, "recall_proxy": 0.5},
        "COMPATIBLE_WITH": {"live_edges": 60, "precision_proxy": 0.85, "recall_proxy": 0.4},
    },
    "summary": {
        "edge_types_present": ["ALTERNATIVE_TO", "COMPATIBLE_WITH", "DEPENDS_ON", "EXTENDS"],
        "total_edges": 470,
    },
    "notes": ["Local OSS stub: Postgres unavailable; serving static fallback payload."],
}


class Handler(BaseHTTPRequestHandler):
    server_version = "ReporiumLocalStub/1.0"

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # quieter logs
        print("[stub] " + (fmt % args))

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            body = b"<!doctype html><html><body><h1>Reporium (local stub)</h1></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "service": "reporium-local-stub"})
            return
        if self.path.startswith("/metrics/graph-quality"):
            if not self.headers.get("X-Admin-Key"):
                self._send_json(401, {"available": False, "error": "missing X-Admin-Key"})
                return
            payload = _pg_graph_quality() or dict(_STATIC_GRAPH_QUALITY)
            self._send_json(200, payload)
            return
        self._send_json(404, {"error": "not found", "path": self.path})

    def do_POST(self):
        if self.path.startswith("/intelligence/ask/stream"):
            if not self.headers.get("X-App-Token"):
                self._send_json(401, {"error": "missing X-App-Token"})
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            _ = self.rfile.read(length) if length else b""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            def emit(obj: dict) -> None:
                self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode("utf-8"))
                self.wfile.flush()

            emit({"type": "sources", "sources": [
                {"repo": "weaviate", "category": "vector_search"},
                {"repo": "qdrant", "category": "vector_search"},
                {"repo": "pgvector", "category": "embeddings"},
            ]})
            for tok in _CANNED_TOKENS:
                emit({"type": "token", "text": tok})
                time.sleep(0.01)
            emit({"type": "done"})
            return
        self._send_json(404, {"error": "not found", "path": self.path})


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[stub] Reporium local contract stub listening on {HOST}:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
