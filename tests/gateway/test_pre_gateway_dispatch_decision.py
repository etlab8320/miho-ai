"""Decision policy tests for pre_gateway_dispatch hook results."""

from __future__ import annotations

from gateway.decision_twin import DecisionTwinProfile
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


def test_pre_gateway_dispatch_decision_twin_prefers_required_tool_candidate() -> None:
    decision = resolve_pre_gateway_dispatch([
        {
            "action": "respond",
            "text": "일반 답변",
            "route": "generic",
            "reason": "fallback",
            "priority": 999,
            "confidence": 0.99,
        },
        {
            "action": "rewrite",
            "text": "life_record_ingest_pdf 도구로 첨부 파일을 저장해.",
            "route": "life_record",
            "reason": "supported_document",
            "intent": "life_record.ingest",
            "confidence": 0.81,
            "required_tool": "life_record_ingest_pdf",
            "evidence": ["supported_attachment"],
            "priority": 10,
        },
    ])

    assert decision.action == "rewrite"
    assert decision.route == "life_record"
    assert decision.required_tool == "life_record_ingest_pdf"
    assert decision.decision_twin == "required_tool_first"
    assert "required_tool:life_record_ingest_pdf" in decision.memory_evidence


def test_pre_gateway_dispatch_decision_twin_can_be_disabled_for_compatibility() -> None:
    profile = DecisionTwinProfile(prefer_required_tool_candidates=False)

    decision = resolve_pre_gateway_dispatch([
        {
            "action": "respond",
            "text": "일반 답변",
            "route": "generic",
            "priority": 999,
            "confidence": 0.99,
        },
        {
            "action": "rewrite",
            "text": "life_record_ingest_pdf 도구로 첨부 파일을 저장해.",
            "route": "life_record",
            "intent": "life_record.ingest",
            "confidence": 0.81,
            "required_tool": "life_record_ingest_pdf",
            "priority": 10,
        },
    ], decision_twin_profile=profile)

    assert decision.route == "generic"
    assert decision.decision_twin == "legacy_rank"
