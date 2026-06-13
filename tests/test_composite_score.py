"""Composite-score coverage for compute_trust_score and the score model.

The existing suite (test_quality_subscore.py) pins the KAN-174 Quality
sub-score behavior. This module covers the parts of the composite model that
were previously untested:

1. Integrity and freshness are hard-coded placeholders at exactly 1.0
   (Phases 4-5). If a future change wires them up, the maintainer must update
   these tests on purpose.
2. Weight normalization: every sub-score term stays in [0, 1] and the
   composite stays in [0, 100] across a sweep of synthetic inputs, including
   degenerate ones (no probes, all probes failing, mixed health).
3. The dead-family fix at the *composite* level: a single dead edge family
   (live_edges=0) lowers the composite via partial coverage instead of
   hard-failing it -- the regression observed 2026-05-12.

All inputs are synthetic dicts. No network, no tokens, no live probes.
"""
from __future__ import annotations

import pytest

from lib.score import compute_trust_score, quality_subscore

# Weight constants mirrored from the composite formula in lib/score.py.
# Pinned here so a silent reweight in score.py is caught by the model tests.
W_RELIABILITY = 30
W_QUALITY = 35
W_INTEGRITY = 20
W_FRESHNESS = 15
W_TOTAL = W_RELIABILITY + W_QUALITY + W_INTEGRITY + W_FRESHNESS


def _healthy_health() -> dict:
    return {"home_status": 200, "api_health_status": 200}


def _healthy_ask(n: int = 3) -> dict:
    return {"probes": [{"completed": True} for _ in range(n)]}


def _all_healthy_graph_quality() -> dict:
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
# Weight model: the four weights sum to 100 (a perfect score is 100.0).
# ---------------------------------------------------------------------------


def test_weights_sum_to_100():
    """A perfect, fully-normalized score must land on exactly 100.0.

    The README and the formula docstring both promise composite==100.0 at a
    perfect score; that only holds if the four weights sum to 100.
    """
    assert W_TOTAL == 100


def test_perfect_inputs_hit_the_weight_total():
    """reliability=quality=integrity=freshness=1.0 -> composite == W_TOTAL."""
    metrics = {
        "available": True,
        "edge_types": {
            "DEPENDS_ON": {"live_edges": 10, "precision": 1.0},
            "ALTERNATIVE_TO": {"live_edges": 10, "precision_proxy": 1.0},
            "EXTENDS": {"live_edges": 10, "precision_proxy": 1.0},
            "COMPATIBLE_WITH": {"live_edges": 10, "precision_proxy": 1.0},
        },
    }
    score = compute_trust_score(_healthy_health(), _healthy_ask(), metrics)
    assert score["reliability"] == 1.0
    assert score["quality"] == 1.0
    assert score["composite"] == float(W_TOTAL)


# ---------------------------------------------------------------------------
# Integrity / freshness placeholders (Phases 4-5).
# ---------------------------------------------------------------------------


def test_integrity_and_freshness_are_placeholder_one():
    """Both are hard-coded to 1.0 until Phases 4-5 wire them up."""
    score = compute_trust_score(
        _healthy_health(), _healthy_ask(), _all_healthy_graph_quality()
    )
    assert score["integrity"] == 1.0
    assert score["freshness"] == 1.0


def test_placeholders_hold_even_when_other_terms_collapse():
    """Integrity/freshness stay at 1.0 even when reliability and quality are 0.

    This proves they are *placeholders* (constant), not derived from inputs.
    """
    score = compute_trust_score(
        {"home_status": 500, "api_health_status": 500},
        {"probes": []},
        {"available": False, "error": "boom"},
    )
    assert score["reliability"] == 0.0
    assert score["quality"] == 0.0
    assert score["integrity"] == 1.0
    assert score["freshness"] == 1.0
    # Only the placeholder weights survive: 20 integrity + 15 freshness = 35.
    assert score["composite"] == float(W_INTEGRITY + W_FRESHNESS)


# ---------------------------------------------------------------------------
# Normalization: every term in [0, 1], composite in [0, 100].
# ---------------------------------------------------------------------------

# (home, api, probes, graph_quality) synthetic scenarios spanning the space.
_HEALTH_CASES = [
    {"home_status": 200, "api_health_status": 200},
    {"home_status": 500, "api_health_status": 200},
    {"home_status": 200, "api_health_status": 503},
    {"home_status": 500, "api_health_status": 500},
    {},  # missing keys -> both treated as not-ok
]

_ASK_CASES = [
    {"probes": [{"completed": True}, {"completed": True}]},
    {"probes": [{"completed": True}, {"completed": False}]},
    {"probes": [{"completed": False}, {"completed": False}]},
    {"probes": []},  # no probes -> error_rate 1.0
    {},  # missing probes key
]

_GQ_CASES = [
    None,
    {"available": False, "error": "boom"},
    {"available": True, "edge_types": {}},
    {
        "available": True,
        "edge_types": {
            "DEPENDS_ON": {"live_edges": 250, "precision": 1.0},
            "ALTERNATIVE_TO": {"live_edges": 120, "precision_proxy": 0.95},
            "EXTENDS": {"live_edges": 40, "precision_proxy": 0.9},
            "COMPATIBLE_WITH": {"live_edges": 60, "precision_proxy": 0.85},
        },
    },
    {
        "available": True,
        "edge_types": {
            "DEPENDS_ON": {"live_edges": 250, "precision": 1.0},
            "ALTERNATIVE_TO": {"live_edges": 0, "precision_proxy": None},
            "EXTENDS": {"live_edges": 40, "precision_proxy": 0.9},
            "COMPATIBLE_WITH": {"live_edges": 60, "precision_proxy": 0.85},
        },
    },
]


@pytest.mark.parametrize("health", _HEALTH_CASES)
@pytest.mark.parametrize("ask", _ASK_CASES)
@pytest.mark.parametrize("graph_quality", _GQ_CASES)
def test_all_terms_normalized_and_composite_bounded(health, ask, graph_quality):
    """Sub-score terms in [0,1]; composite in [0, W_TOTAL]; no NaN/negatives."""
    score = compute_trust_score(health, ask, graph_quality)
    for term in ("reliability", "quality", "integrity", "freshness"):
        value = score[term]
        assert 0.0 <= value <= 1.0, f"{term}={value} out of [0,1]"
    assert 0.0 <= score["error_rate"] <= 1.0
    assert 0.0 <= score["composite"] <= float(W_TOTAL)


def test_error_rate_one_when_no_probes():
    """No probes is a total failure, not a divide-by-zero / silent pass."""
    score = compute_trust_score(_healthy_health(), {"probes": []}, None)
    assert score["error_rate"] == 1.0
    assert score["reliability"] == 0.0


def test_error_rate_half_when_one_of_two_probes_fail():
    """Partial probe failure scales reliability proportionally."""
    score = compute_trust_score(
        _healthy_health(),
        {"probes": [{"completed": True}, {"completed": False}]},
        None,
    )
    assert score["error_rate"] == 0.5
    assert score["reliability"] == 0.5


def test_reliability_is_zero_if_home_down_even_with_probes_passing():
    """Reliability is multiplicative: any hard gate at 0 zeroes the term."""
    score = compute_trust_score(
        {"home_status": 500, "api_health_status": 200},
        _healthy_ask(),
        None,
    )
    assert score["reliability"] == 0.0


# ---------------------------------------------------------------------------
# Dead-family fix at the composite level (regression 2026-05-12).
# ---------------------------------------------------------------------------


def test_dead_family_lowers_composite_via_partial_coverage_not_hard_fail():
    """One dead family (live_edges=0) must lower the composite, not zero it.

    Before the fix, a 0-edge family with null precision coerced to 0.0 and
    tripped the floor, hard-failing quality to 0.0 (composite dragged to 65).
    The fix short-circuits dead families, so quality reflects partial coverage
    and the composite lands strictly between the hard-fail floor (65) and the
    all-live ceiling.
    """
    metrics = _all_healthy_graph_quality()
    # COMPATIBLE_WITH dead with the real production shape: 0 edges, null proxy.
    metrics["edge_types"]["COMPATIBLE_WITH"] = {
        "live_edges": 0,
        "precision_proxy": None,
    }

    # All-live baseline for the same fixture (for the ceiling comparison).
    baseline = compute_trust_score(
        _healthy_health(), _healthy_ask(), _all_healthy_graph_quality()
    )
    degraded = compute_trust_score(_healthy_health(), _healthy_ask(), metrics)

    # quality = mean(1.0, 0.95, 0.9, 0.0) over 4 families = 0.7125, and the
    # dict rounds the term to 3 decimals (0.7125 -> 0.713, banker's rounding).
    expected_quality = round((1.0 + 0.95 + 0.9 + 0.0) / 4, 3)
    assert degraded["quality"] == expected_quality
    assert quality_subscore(metrics) == pytest.approx((1.0 + 0.95 + 0.9) / 4)

    # NOT a hard fail: quality stays above zero, composite above the 65 floor.
    assert degraded["quality"] > 0.0
    hard_fail_floor = float(W_RELIABILITY + W_INTEGRITY + W_FRESHNESS)  # 65.0
    assert degraded["composite"] > hard_fail_floor
    # Partial coverage costs us vs the all-live baseline.
    assert degraded["composite"] < baseline["composite"]


def test_dead_family_composite_matches_manual_formula():
    """Pin the exact composite for the dead-family case to a hand computation."""
    metrics = _all_healthy_graph_quality()
    metrics["edge_types"]["COMPATIBLE_WITH"] = {
        "live_edges": 0,
        "precision_proxy": None,
    }
    quality = quality_subscore(metrics)  # 0.7125
    score = compute_trust_score(_healthy_health(), _healthy_ask(), metrics)
    expected = round(
        W_RELIABILITY * 1.0
        + W_QUALITY * quality
        + W_INTEGRITY * 1.0
        + W_FRESHNESS * 1.0,
        1,
    )
    assert score["composite"] == expected


def test_two_dead_families_still_partial_not_hard_fail():
    """Two dead families keep partial-coverage semantics (no hard fail)."""
    metrics = _all_healthy_graph_quality()
    metrics["edge_types"]["EXTENDS"] = {"live_edges": 0, "precision_proxy": None}
    metrics["edge_types"]["COMPATIBLE_WITH"] = {
        "live_edges": 0,
        "precision_proxy": None,
    }
    score = compute_trust_score(_healthy_health(), _healthy_ask(), metrics)
    # quality = mean(1.0, 0.95, 0.0, 0.0) = 0.4875 -> still > 0, no hard fail.
    # The raw sub-score is exact; the dict term is rounded to 3 decimals.
    assert quality_subscore(metrics) == pytest.approx((1.0 + 0.95) / 4)
    assert score["quality"] == round((1.0 + 0.95) / 4, 3)
    assert score["quality"] > 0.0
    assert score["composite"] > float(W_RELIABILITY + W_INTEGRITY + W_FRESHNESS)
