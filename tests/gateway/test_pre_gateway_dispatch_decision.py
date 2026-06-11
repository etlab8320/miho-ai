"""Decision policy tests for pre_gateway_dispatch hook results."""

from __future__ import annotations

from gateway.pre_dispatch import resolve_pre_gateway_dispatch


def test_pre_gateway_dispatch_picks_highest_priority_response() -> None:
    decision = resolve_pre_gateway_dispatch([
        {"action": "respond", "text": "low", "route": "generic", "priority": 0},
        {"action": "respond", "text": "high", "route": "life_record", "priority": 100},
    ])

    assert decision.action == "respond"
    assert decision.text == "high"
    assert decision.route == "life_record"
    assert len(decision.candidates) == 2


def test_pre_gateway_dispatch_keeps_legacy_first_candidate_when_priority_ties() -> None:
    decision = resolve_pre_gateway_dispatch([
        {"action": "respond", "text": "first", "route": "first"},
        {"action": "respond", "text": "second", "route": "second"},
    ])

    assert decision.action == "respond"
    assert decision.text == "first"
    assert decision.route == "first"


def test_pre_gateway_dispatch_ignores_allow_for_final_decision() -> None:
    decision = resolve_pre_gateway_dispatch([
        {"action": "allow", "route": "context_capture"},
        {"action": "rewrite", "text": "tool request", "route": "life_record", "reason": "document"},
    ])

    assert decision.action == "rewrite"
    assert decision.text == "tool request"
    assert decision.reason == "document"
