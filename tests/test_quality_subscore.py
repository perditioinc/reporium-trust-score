"""Synthetic regression tests for KAN-174 Quality sub-score sensitivity.

The hourly probe was returning composite=1.0 even when KAN-147's nightly
graph-quality invariants were firing. These tests pin the new behavior:

1. EXTENDS.precision_proxy=0.0 -> composite drops to 0.0 (was 1.0 before fix).
2. All families healthy -> composite stays at 1.0.
3. ALTERNATIVE_TO.live_edges=0 with precision=0.95 -> that family contributes
   0; composite reflects partial coverage rather than a hard fail.
"""
from __future__ import annotations

from lib.score import PRECISION_FLOOR, compute_trust_score, quality_subscore


def _healthy_health() -> dict:
    return {"home_status": 200, "api_health_status": 200}


def _healthy_ask() -> dict:
    return {
        "probes": [
            {"completed": True},
            {"completed": True},
            {"completed": True},
        ]
    }


def _all_healthy_graph_quality() -> dict:
    """Every edge family above the floor and with live edges."""
    return {
        "available": True,
        "edge_types": {
            "DEPENDS_ON": {"live_edges": 250, "precision": 1.0},
            "ALTERNATIVE_TO": {"live_edges": 120, "precision_proxy": 0.95},
            "EXTENDS": {"live_edges": 40, "precision_proxy": 0.9},
            "COMPATIBLE_WITH": {"live_edges": 60, "precision_proxy": 0.85},
        },
    }


# ---------------------------------------------------------------------------
# quality_subscore unit tests
# ---------------------------------------------------------------------------


def test_quality_hard_fails_when_extends_precision_zero():
    """The headline regression: EXTENDS=0.0 must drop quality (and composite) to 0."""
    metrics = _all_healthy_graph_quality()
    metrics["edge_types"]["EXTENDS"]["precision_proxy"] = 0.0
    assert quality_subscore(metrics) == 0.0


def test_quality_hard_fails_when_alternative_below_floor():
    """ALTERNATIVE_TO=0.66 (today's live state, < 0.7 floor) must hard-fail."""
    metrics = _all_healthy_graph_quality()
    metrics["edge_types"]["ALTERNATIVE_TO"]["precision_proxy"] = 0.66
    assert quality_subscore(metrics) == 0.0


def test_quality_above_floor_when_all_healthy():
    """All families >= floor and live -> nonzero average."""
    metrics = _all_healthy_graph_quality()
    score = quality_subscore(metrics)
    assert score > 0.0
    assert score <= 1.0


def test_quality_partial_when_one_family_dead():
    """ALTERNATIVE_TO live_edges=0 with precision=0.95 contributes 0,
    but the remaining 3 families with precision 1.0/0.9/0.85 should still
    pull quality up to a partial-coverage value (~0.6875) -- not hard-fail.
    """
    metrics = _all_healthy_graph_quality()
    metrics["edge_types"]["ALTERNATIVE_TO"] = {
        "live_edges": 0,
        "precision_proxy": 0.95,
    }
    score = quality_subscore(metrics)
    expected = (1.0 + 0.0 + 0.9 + 0.85) / 4
    assert score == expected
    assert 0.0 < score < 1.0


def test_quality_dead_family_with_null_precision_does_not_hard_fail():
    """COMPATIBLE_WITH (and other proxy families) routinely emit
    `precision_proxy: null` when `live_edges=0`. Previously this null
    coerced to 0.0 which tripped the precision floor and hard-failed the
    whole composite (production regression observed 2026-05-12: composite
    dragged to 65 even with 3/4 live families above floor). The fix
    short-circuits on `live_edges == 0` BEFORE the floor check.
    """
    metrics = _all_healthy_graph_quality()
    # Live-shape COMPATIBLE_WITH from production: 0 edges, null precision.
    metrics["edge_types"]["COMPATIBLE_WITH"] = {
        "live_edges": 0,
        "eligible_repos": 0,
        "observed_repos": 0,
        "precision_proxy": None,
        "recall_proxy": None,
        "invalid_live_edges": 0,
    }
    score = quality_subscore(metrics)
    # _all_healthy_graph_quality fixture sets ALT=0.95, EXT=0.9, DEP=0.85.
    # Dead COMPATIBLE_WITH contributes 0.
    expected = (1.0 + 0.95 + 0.9 + 0.0) / 4
    assert score == expected
    assert score > 0.0  # MUST not hard-fail


def test_quality_zero_when_metrics_missing():
    """A failed probe (available=False) is treated as regression, not green pass."""
    assert quality_subscore({"available": False, "error": "boom"}) == 0.0
    assert quality_subscore(None) == 0.0
    assert quality_subscore({}) == 0.0


def test_quality_zero_when_edge_types_empty():
    """Empty edge_types dict means we have no signal -> 0.0."""
    assert quality_subscore({"available": True, "edge_types": {}}) == 0.0


def test_quality_handles_missing_edge_family():
    """If the API ever drops a family, treat it as live_edges=0/precision=0.

    Today the API always returns all four families, but we don't want a future
    schema change to silently flip the score to a false green. A missing
    family means precision defaults to 0.0 which trips the floor -> 0.0.
    """
    metrics = _all_healthy_graph_quality()
    del metrics["edge_types"]["EXTENDS"]
    assert quality_subscore(metrics) == 0.0


def test_floor_constant_matches_kan147():
    """Pin the floor to KAN-147's 0.7. If this changes, the JIRA must too."""
    assert PRECISION_FLOOR == 0.7


# ---------------------------------------------------------------------------
# compute_trust_score integration tests
# ---------------------------------------------------------------------------


def test_composite_drops_to_below_baseline_when_extends_zero():
    """The headline KAN-174 fix: composite was flat at 100.0 before; now drops."""
    metrics = _all_healthy_graph_quality()
    metrics["edge_types"]["EXTENDS"]["precision_proxy"] = 0.0
    score = compute_trust_score(_healthy_health(), _healthy_ask(), metrics)
    # Before fix: composite=100.0 even with EXTENDS dead.
    # After fix:  reliability=1, quality=0, integrity=1, freshness=1
    #             -> 30*1 + 35*0 + 20*1 + 15*1 = 65.0
    assert score["quality"] == 0.0
    assert score["composite"] == 65.0


def test_composite_full_when_everything_healthy():
    """Healthy reliability + healthy graph -> 100.0."""
    score = compute_trust_score(
        _healthy_health(), _healthy_ask(), _all_healthy_graph_quality()
    )
    # reliability=1.0, quality<=1.0 (avg of 1.0/0.95/0.9/0.85 = 0.925)
    # composite = 30 + 35*0.925 + 20 + 15 = 97.4
    assert score["reliability"] == 1.0
    assert score["composite"] < 100.0  # quality < 1 because not all families == 1.0
    assert score["composite"] > 90.0


def test_composite_full_when_all_precision_one():
    """Pure-1.0 precision across all families -> composite==100.0."""
    metrics = {
        "available": True,
        "edge_types": {
            "DEPENDS_ON": {"live_edges": 250, "precision": 1.0},
            "ALTERNATIVE_TO": {"live_edges": 120, "precision_proxy": 1.0},
            "EXTENDS": {"live_edges": 40, "precision_proxy": 1.0},
            "COMPATIBLE_WITH": {"live_edges": 60, "precision_proxy": 1.0},
        },
    }
    score = compute_trust_score(_healthy_health(), _healthy_ask(), metrics)
    assert score["composite"] == 100.0


def test_composite_when_graph_quality_unavailable():
    """Probe failure -> quality=0 -> composite ceiling = 30+0+20+15 = 65."""
    score = compute_trust_score(
        _healthy_health(),
        _healthy_ask(),
        {"available": False, "error": "REPORIUM_ADMIN_KEY not set; skipping"},
    )
    assert score["quality"] == 0.0
    assert score["composite"] == 65.0


def test_composite_reflects_today_live_regression_state():
    """Anchor test: today's reported regression state from KAN-174 description.

    - ALTERNATIVE_TO precision_proxy=0.66 (below floor)
    - EXTENDS precision_proxy=0.0
    - DEPENDS_ON live_edges=89, precision=1.0 (corpus reality)
    - COMPATIBLE_WITH live_edges=0

    Quality should hard-fail to 0.0 (any family below floor wins).
    Composite = 30 + 0 + 20 + 15 = 65.0, not the false-green 100.0 we had.
    """
    metrics = {
        "available": True,
        "edge_types": {
            "DEPENDS_ON": {"live_edges": 89, "precision": 1.0},
            "ALTERNATIVE_TO": {"live_edges": 80, "precision_proxy": 0.66},
            "EXTENDS": {"live_edges": 30, "precision_proxy": 0.0},
            "COMPATIBLE_WITH": {"live_edges": 0, "precision_proxy": 0.0},
        },
    }
    score = compute_trust_score(_healthy_health(), _healthy_ask(), metrics)
    assert score["quality"] == 0.0
    assert score["composite"] == 65.0
