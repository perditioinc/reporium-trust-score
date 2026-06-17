"""Coverage for `compute_trust_score` beyond the Quality sub-score.

`tests/test_quality_subscore.py` pins the KAN-174 Quality behavior. This file
pins the parts of the composite that were previously untested:

1. The reliability term (home/api status flags, error_rate from probe
   completion, the empty-probes edge case).
2. The integrity/freshness placeholders, which are documented as a flat 1.0
   until Phases 4-5 wire them up. A future change to those phases must update
   these tests deliberately rather than drift silently.
3. The normalization invariant: every sub-score stays in [0, 1] and the
   composite stays in [0, 100] across a spread of synthetic inputs.
4. The dead-family fix at the COMPOSITE level (not just inside
   `quality_subscore`): the 2026-05-12 production regression where a
   live_edges=0 family with null precision dragged the composite to 65 even
   though every live family was above floor.

All inputs are OFFLINE synthetic dicts -- no probes, no network, no tokens.
"""
from __future__ import annotations

import pytest

from lib.score import compute_trust_score


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
    return {
        "available": True,
        "edge_types": {
            "DEPENDS_ON": {"live_edges": 250, "precision": 1.0},
            "ALTERNATIVE_TO": {"live_edges": 120, "precision_proxy": 1.0},
            "EXTENDS": {"live_edges": 40, "precision_proxy": 1.0},
            "COMPATIBLE_WITH": {"live_edges": 60, "precision_proxy": 1.0},
        },
    }


# ---------------------------------------------------------------------------
# Reliability term
# ---------------------------------------------------------------------------


def test_reliability_one_when_all_signals_green():
    score = compute_trust_score(
        _healthy_health(), _healthy_ask(), _all_healthy_graph_quality()
    )
    assert score["reliability"] == 1.0
    assert score["error_rate"] == 0.0


def test_reliability_zero_when_home_down():
    """Home page non-200 zeroes reliability (multiplicative gate)."""
    health = {"home_status": 503, "api_health_status": 200}
    score = compute_trust_score(health, _healthy_ask(), _all_healthy_graph_quality())
    assert score["reliability"] == 0.0


def test_reliability_zero_when_api_down():
    """API /health non-200 zeroes reliability even if home is up."""
    health = {"home_status": 200, "api_health_status": 500}
    score = compute_trust_score(health, _healthy_ask(), _all_healthy_graph_quality())
    assert score["reliability"] == 0.0


def test_reliability_zero_when_home_status_missing():
    """A health payload missing home_status must not pass the 200 gate."""
    health = {"api_health_status": 200}
    score = compute_trust_score(health, _healthy_ask(), _all_healthy_graph_quality())
    assert score["reliability"] == 0.0


def test_error_rate_reflects_partial_probe_completion():
    """1 of 3 probes failing -> error_rate ~= 0.333, reliability scaled by it."""
    ask = {
        "probes": [
            {"completed": True},
            {"completed": True},
            {"completed": False},
        ]
    }
    score = compute_trust_score(_healthy_health(), ask, _all_healthy_graph_quality())
    assert score["error_rate"] == pytest.approx(0.333, abs=1e-3)
    # reliability = home(1) * api(1) * (1 - 0.3333...) = 0.6666...
    assert score["reliability"] == pytest.approx(0.667, abs=1e-3)


def test_error_rate_one_when_no_probes():
    """Empty probe list is a total reliability failure, not a free pass."""
    score = compute_trust_score(
        _healthy_health(), {"probes": []}, _all_healthy_graph_quality()
    )
    assert score["error_rate"] == 1.0
    assert score["reliability"] == 0.0


def test_error_rate_one_when_probes_key_missing():
    """An ask payload with no `probes` key behaves like zero probes."""
    score = compute_trust_score(_healthy_health(), {}, _all_healthy_graph_quality())
    assert score["error_rate"] == 1.0
    assert score["reliability"] == 0.0


# ---------------------------------------------------------------------------
# Integrity / freshness placeholders (Phases 4-5)
# ---------------------------------------------------------------------------


def test_integrity_and_freshness_are_placeholder_one():
    """Documented invariant: until Phases 4-5 land these are a flat 1.0.

    If a future phase wires real signals in, this test should be updated
    deliberately -- it is a tripwire against silent drift, not a spec.
    """
    score = compute_trust_score(
        _healthy_health(), _healthy_ask(), _all_healthy_graph_quality()
    )
    assert score["integrity"] == 1.0
    assert score["freshness"] == 1.0


def test_placeholders_hold_even_when_reliability_and_quality_collapse():
    """Integrity/freshness stay at 1.0 regardless of the measured terms."""
    health = {"home_status": 0, "api_health_status": 0}
    score = compute_trust_score(health, {"probes": []}, None)
    assert score["reliability"] == 0.0
    assert score["quality"] == 0.0
    assert score["integrity"] == 1.0
    assert score["freshness"] == 1.0
    # Only the two placeholder terms remain: 20*1 + 15*1 = 35.0
    assert score["composite"] == 35.0


# ---------------------------------------------------------------------------
# Normalization invariant: sub-scores in [0,1], composite in [0,100]
# ---------------------------------------------------------------------------

_HEALTH_CASES = [
    {"home_status": 200, "api_health_status": 200},
    {"home_status": 503, "api_health_status": 200},
    {"home_status": 200, "api_health_status": 500},
    {},
]

_ASK_CASES = [
    _healthy_ask(),
    {"probes": [{"completed": True}, {"completed": False}]},
    {"probes": []},
    {},
]

_GRAPH_CASES = [
    _all_healthy_graph_quality(),
    None,
    {"available": False, "error": "boom"},
    {
        "available": True,
        "edge_types": {
            "DEPENDS_ON": {"live_edges": 89, "precision": 1.0},
            "ALTERNATIVE_TO": {"live_edges": 80, "precision_proxy": 0.66},
            "EXTENDS": {"live_edges": 30, "precision_proxy": 0.0},
            "COMPATIBLE_WITH": {"live_edges": 0, "precision_proxy": None},
        },
    },
]


@pytest.mark.parametrize("health", _HEALTH_CASES)
@pytest.mark.parametrize("ask", _ASK_CASES)
@pytest.mark.parametrize("graph", _GRAPH_CASES)
def test_subscores_normalized_and_composite_bounded(health, ask, graph):
    """Every sub-score must stay in [0,1] and composite in [0,100]."""
    score = compute_trust_score(health, ask, graph)
    for term in ("reliability", "quality", "integrity", "freshness", "error_rate"):
        assert 0.0 <= score[term] <= 1.0, f"{term}={score[term]} out of [0,1]"
    assert 0.0 <= score["composite"] <= 100.0


def test_composite_equals_weighted_sum_of_subscores():
    """Composite is 30R + 35Q + 20I + 15F.

    Cross-check against an independent recomputation from the returned
    sub-scores (defends the weight constants 30/35/20/15 against drift). The
    composite is rounded from the UNROUNDED sub-scores, while this check sees
    only the 3-decimal rounded `quality`, so allow a small tolerance for that
    rounding gap (max ~0.018 from 35 * 5e-4) plus the composite's own 1-decimal
    rounding. The 0.1 band is still an order of magnitude tighter than any
    single-unit weight-constant drift would produce.
    """
    metrics = {
        "available": True,
        "edge_types": {
            "DEPENDS_ON": {"live_edges": 250, "precision": 1.0},
            "ALTERNATIVE_TO": {"live_edges": 120, "precision_proxy": 0.8},
            "EXTENDS": {"live_edges": 40, "precision_proxy": 0.9},
            "COMPATIBLE_WITH": {"live_edges": 60, "precision_proxy": 0.85},
        },
    }
    score = compute_trust_score(_healthy_health(), _healthy_ask(), metrics)
    expected = (
        30 * score["reliability"]
        + 35 * score["quality"]
        + 20 * score["integrity"]
        + 15 * score["freshness"]
    )
    assert score["composite"] == pytest.approx(round(expected, 1), abs=0.1)


# ---------------------------------------------------------------------------
# Dead-family fix at the COMPOSITE level (2026-05-12 production regression)
# ---------------------------------------------------------------------------


def test_dead_family_yields_partial_composite_not_hard_fail():
    """COMPATIBLE_WITH live_edges=0 / precision_proxy=null must NOT hard-fail.

    Production 2026-05-12: a dead family with null precision tripped the floor
    and dragged composite to 65 even though all three live families were above
    floor. The fix short-circuits on live_edges==0. End-to-end, quality should
    be the partial mean (1.0 + 1.0 + 1.0 + 0.0)/4 = 0.75, and composite should
    sit strictly between the hard-fail floor (65.0) and a perfect 100.0.
    """
    metrics = _all_healthy_graph_quality()
    metrics["edge_types"]["COMPATIBLE_WITH"] = {
        "live_edges": 0,
        "precision_proxy": None,
    }
    score = compute_trust_score(_healthy_health(), _healthy_ask(), metrics)
    assert score["quality"] == pytest.approx(0.75)
    # 30*1 + 35*0.75 + 20*1 + 15*1 = 91.25 -> rounded 91.2/91.3
    assert score["composite"] == pytest.approx(91.25, abs=0.06)
    assert 65.0 < score["composite"] < 100.0


def test_below_floor_live_family_still_hard_fails_composite():
    """A genuinely below-floor LIVE family must still hard-fail (no regression
    masking). This is the complement of the dead-family case: dead families are
    forgiven, but a live family under 0.7 is a real regression.
    """
    metrics = _all_healthy_graph_quality()
    metrics["edge_types"]["EXTENDS"] = {"live_edges": 40, "precision_proxy": 0.5}
    score = compute_trust_score(_healthy_health(), _healthy_ask(), metrics)
    assert score["quality"] == 0.0
    # reliability=1, quality=0, integrity=1, freshness=1 -> 65.0
    assert score["composite"] == 65.0
