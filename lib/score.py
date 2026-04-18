"""Composite trust score.

Phase 1: Reliability term is measured. Quality, Integrity, Freshness are
placeholders (1.0) and will come online in Phases 4-5.

Weights: 30 reliability + 35 quality + 20 integrity + 15 freshness = 100.
"""
from __future__ import annotations


def compute_trust_score(health: dict, ask_results: dict) -> dict:
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
    quality = 1.0      # Phase 5 will implement
    integrity = 1.0    # Phase 4 will implement
    freshness = 1.0    # Phase 5 will implement
    composite = 30 * reliability + 35 * quality + 20 * integrity + 15 * freshness
    return {
        "composite": round(composite, 1),
        "reliability": round(reliability, 3),
        "quality": quality,
        "integrity": integrity,
        "freshness": freshness,
        "error_rate": round(error_rate, 3),
    }
