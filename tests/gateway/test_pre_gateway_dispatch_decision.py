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


def test_pre_gateway_dispatch_uses_confidence_when_priority_ties() -> None:
    decision = resolve_pre_gateway_dispatch([
        {
            "action": "respond",
            "text": "weak",
            "route": "academy_ops",
            "priority": 30,
            "confidence": 0.55,
        },
        {
            "action": "respond",
            "text": "strong",
            "route": "academy_ops",
            "priority": 30,
            "confidence": 0.9,
            "intent": "academy.student_record.lookup",
            "required_tool": "academy_student_record_lookup",
            "evidence": ["학생 기록 요청", "최근 기록"],
        },
    ])

    assert decision.text == "strong"
    assert decision.intent == "academy.student_record.lookup"
    assert decision.required_tool == "academy_student_record_lookup"
    assert decision.evidence == ("학생 기록 요청", "최근 기록")


def test_pre_gateway_dispatch_ignores_allow_for_final_decision() -> None:
    decision = resolve_pre_gateway_dispatch([
        {"action": "allow", "route": "context_capture"},
        {"action": "rewrite", "text": "tool request", "route": "life_record", "reason": "document"},
    ])

    assert decision.action == "rewrite"
    assert decision.text == "tool request"
    assert decision.reason == "document"
