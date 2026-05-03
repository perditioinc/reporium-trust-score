"""Composite trust score.

Phase 1: Reliability term is measured.
KAN-174: Quality term is now wired to the live `/metrics/graph-quality`
snapshot so the hourly probe stops returning composite=1.0 when KAN-147's
nightly invariants are firing on real regressions. Integrity and freshness
remain placeholders (Phases 4-5).

Weights: 30 reliability + 35 quality + 20 integrity + 15 freshness = 100.
"""
from __future__ import annotations

# Edge families the graph-quality endpoint exposes today. Quality sub-score
# weighs each one by its precision_proxy AND requires non-zero live edges,
# so a "functionally dead" type (live_edges=0) contributes 0 to the average.
EDGE_TYPES = ("DEPENDS_ON", "ALTERNATIVE_TO", "EXTENDS", "COMPATIBLE_WITH")

# KAN-147 invariant floor. If ANY family's precision drops below this, the
# Quality sub-score hard-fails to 0.0 -- this is what makes the probe LOUD
# when a regression fires (correctness audit P1, 2026-04-29).
PRECISION_FLOOR = 0.7


def quality_subscore(graph_quality_metrics: dict | None) -> float:
    """Quality sub-score weighted by edge-count x precision_proxy per family.

    Hard-fails to 0.0 if ANY edge family's precision is below
    :data:`PRECISION_FLOOR`. Otherwise returns the unweighted mean of
    `precision * (1 if live_edges > 0 else 0)` across all four edge types,
    so a dead family pulls the score down without crashing on missing data.

    If the metrics payload is missing/unavailable (probe failure), returns
    0.0 -- a missing signal is treated as a regression, not as a green pass.
    """
    if not graph_quality_metrics or not graph_quality_metrics.get("available", True):
        return 0.0

    edge_types = graph_quality_metrics.get("edge_types") or {}
    if not edge_types:
        return 0.0

    weighted_scores: list[float] = []
    for et in EDGE_TYPES:
        info = edge_types.get(et) or {}
        # DEPENDS_ON exposes "precision" (exact); the proxies expose
        # "precision_proxy". Treat them interchangeably.
        precision = info.get("precision")
        if precision is None:
            precision = info.get("precision_proxy")
        precision = float(precision) if precision is not None else 0.0
        live_edges = int(info.get("live_edges", 0) or 0)

        # Hard-fail composite when any family falls below the KAN-147 floor.
        if precision < PRECISION_FLOOR:
            return 0.0

        # Dead family (no live edges) contributes 0 -- partial-coverage
        # regression, not a hard fail.
        weighted_scores.append(precision if live_edges > 0 else 0.0)

    return sum(weighted_scores) / len(EDGE_TYPES)


def compute_trust_score(
    health: dict,
    ask_results: dict,
    graph_quality: dict | None = None,
) -> dict:
    home_ok = health.get("home_status") == 200
    api_ok = health.get("api_health_status") == 200
    probes = ask_results.get("probes", [])
    completed = sum(1 for p in probes if p.get("completed"))
    error_rate = 1 - (completed / len(probes)) if probes else 1.0
    reliability = (
        (1.0 if home_ok else 0.0)
        * (1.0 if api_ok else 0.0)
        * (1 - error_rate)
    )
    quality = quality_subscore(graph_quality)
    integrity = 1.0    # Phase 4 will implement
    freshness = 1.0    # Phase 5 will implement
    composite = 30 * reliability + 35 * quality + 20 * integrity + 15 * freshness
    return {
        "composite": round(composite, 1),
        "reliability": round(reliability, 3),
        "quality": round(quality, 3),
        "integrity": integrity,
        "freshness": freshness,
        "error_rate": round(error_rate, 3),
    }
