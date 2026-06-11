"""Tests for the LLM-backed Miho decision-twin pre-dispatch plugin."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.decision_twin import _decision_twin_pre_gateway_dispatch
from plugins.decision_twin.contracts import decision_tool_contracts
from plugins.decision_twin.router import build_decision_messages, parse_decision_payload, route_result_text


def _event(text: str, *, user_id: str = "u1") -> MessageEvent:
    return MessageEvent(
        text=text,
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id=user_id,
            chat_id="channel-1",
            guild_id="guild-1",
        ),
    )


@pytest.mark.asyncio
async def test_decision_twin_rewrites_to_required_tool_from_llm_judge() -> None:
    async def resolver(_messages):
        return {
            "action": "route",
            "route": "life_record",
            "intent": "life_record.summary",
            "required_tool": "life_record_summary",
            "confidence": 0.92,
            "evidence": ["사용자가 현재 스레드 생기부 요약을 요청했다"],
            "tool_instruction": "현재 스레드 생기부 DB를 요약한다",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("가은이 생기부 핵심만 다시 정리해줘"),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
        owner_context_builder=lambda _text: "생기부는 반드시 life_record_* 도구로 조회한다.",
    )

    assert result["action"] == "rewrite"
    assert result["route"] == "decision_twin"
    assert result["intent"] == "life_record.summary"
    assert result["required_tool"] == "life_record_summary"
    assert result["confidence"] == 0.92
    assert "반드시 `life_record_summary` 도구" in result["text"]
    assert "사용자 원문:" in result["text"]


@pytest.mark.asyncio
async def test_decision_twin_marks_hakjong_report_required_route_for_guard() -> None:
    from gateway.session_context import clear_session_vars, set_session_vars
    from plugins.academy_ops.hakjong_report_guard import (
        _block_after_hakjong_report_package,
        _reset_hakjong_report_package_state,
    )

    async def resolver(_messages):
        return {
            "action": "route",
            "route": "academy_ops",
            "intent": "hakjong.report.package",
            "required_tool": "academy_hakjong_report_package",
            "confidence": 0.94,
            "evidence": ["학생부종합전형 상담용 리포트 PDF/HTML 패키지를 요청했다"],
            "tool_instruction": "프리미엄 학종 리포트 패키지 계약을 사용한다",
        }

    _reset_hakjong_report_package_state()
    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("가은 학생 4개 대학 학종 상담 리포트 파일로 보내줘"),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
    )
    tokens = set_session_vars(platform="discord", chat_id="channel-1")
    try:
        blocked = _block_after_hakjong_report_package(tool_name="execute_code", args={})
    finally:
        clear_session_vars(tokens)

    assert result["required_tool"] == "academy_hakjong_report_package"
    assert blocked and blocked["action"] == "block"


def test_decision_twin_marks_guard_in_runtime_plugin_namespace(monkeypatch) -> None:
    import plugins.decision_twin as decision_twin

    calls: list[tuple[object, str]] = []

    runtime_guard = SimpleNamespace(
        mark_hakjong_report_required_route=lambda event, required_tool="": calls.append((event, required_tool))
    )
    monkeypatch.setitem(sys.modules, "miho_plugins.academy_ops.hakjong_report_guard", runtime_guard)
    monkeypatch.setattr(decision_twin, "__name__", "miho_plugins.decision_twin")
    event = object()

    decision_twin._mark_required_tool_route(event, "academy_hakjong_report_package")

    assert calls == [(event, "academy_hakjong_report_package")]


@pytest.mark.asyncio
async def test_decision_twin_skips_when_sender_is_not_authorized() -> None:
    calls = 0

    async def resolver(_messages):
        nonlocal calls
        calls += 1
        return {"action": "route", "required_tool": "life_record_summary", "confidence": 1}

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("생기부 봐줘", user_id="intruder"),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: False),
        resolver=resolver,
    )

    assert result == {"action": "allow"}
    assert calls == 0


@pytest.mark.asyncio
async def test_decision_twin_allows_low_confidence_or_malformed_payload() -> None:
    async def resolver(_messages):
        return {"action": "route", "required_tool": "life_record_summary", "confidence": 0.41}

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("이거 해줘"),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
    )

    assert result == {"action": "allow"}


def test_decision_prompt_contains_context_and_tool_contracts() -> None:
    messages = build_decision_messages(
        user_text="학종 리포트 파일 보내줘",
        owner_context="학종 리포트는 검증 도구 통과 후 MEDIA로 전달한다.",
        turn_context={"media": [".pdf"], "reply_to_text": "직전 산출물"},
    )
    joined = "\n".join(message["content"] for message in messages)

    assert "JSON만 반환" in joined
    assert "owner_memory" in joined
    assert "tool_contracts" in joined
    assert "academy_hakjong_report_package" in joined
    assert "life_record_summary" in joined
    assert "키워드 하나" in joined


def test_hakjong_report_route_text_forbids_path_or_lock_excuses() -> None:
    decision = parse_decision_payload(
        {
            "action": "route",
            "route": "academy_ops",
            "required_tool": "academy_hakjong_report_package",
            "intent": "학종 리포트 PDF 생성",
            "confidence": 0.94,
            "tool_instruction": "국민대 경희대 인하대 3개 리포트를 만든다",
        }
    )

    text = route_result_text("가은이 3개 학교 학종 리포트로 줘", decision)

    assert "경로가 잠겨 있지 않다" in text
    assert "파일 경로를 사용자에게 묻지 마라" in text
    assert "write_file" in text
    assert "academy_hakjong_report_package" in text


def test_decision_contracts_cover_every_registered_tool() -> None:
    from miho_cli.plugins import discover_plugins
    from tools.registry import discover_builtin_tools, registry

    discover_builtin_tools()
    discover_plugins(force=True)

    contracts = decision_tool_contracts()
    registered_tools = set(registry.get_all_tool_names())
    missing = sorted(registered_tools - set(contracts))

    assert missing == []
    assert contracts["send_message"]["domain"] == "messaging"
    assert contracts["terminal"]["domain"] == "terminal"
    assert contracts["academy_student_card_image"]["domain"] == "academy_ops"


def test_core_domain_contracts_are_not_generic_fallbacks() -> None:
    contracts = decision_tool_contracts()
    core_tools = (
        "life_record_ingest_pdf",
        "life_record_summary",
        "life_record_lookup",
        "academy_hakjong_report_package",
        "academy_render_image",
        "academy_report_image",
        "send_message",
        "jungsi_login",
    )

    for tool_name in core_tools:
        contract = contracts[tool_name]
        purpose = contract["purpose"]
        assert len(purpose) >= 35
        assert not purpose.startswith("Registered Miho tool")
        assert contract["domain"]


@pytest.mark.asyncio
async def test_decision_twin_blocks_jungsi_login_for_hakjong_context() -> None:
    async def resolver(_messages):
        return {
            "action": "route",
            "route": "jungsi",
            "intent": "hakjong.report.login",
            "required_tool": "jungsi_login",
            "confidence": 0.98,
            "evidence": ["학종 리포트 요청을 로그인 문제로 오판했다"],
            "tool_instruction": "정시엔진 로그인 링크를 발급한다",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("말이 좀 긴데 결국 학종 리포트 파일을 제대로 보내달라는 거야"),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
        owner_context_builder=lambda _text: "학종 리포트는 생기부/수시 근거와 premium_hakjong_report 계약을 사용한다.",
    )

    assert result == {"action": "allow"}


def test_parse_decision_payload_accepts_json_string() -> None:
    decision = parse_decision_payload(
        '{"action":"route","route":"academy_ops","required_tool":"academy_student_card_image",'
        '"intent":"academy.student_card","confidence":0.88,"evidence":["학생 카드 요청"]}'
    )

    assert decision.action == "route"
    assert decision.route == "academy_ops"
    assert decision.required_tool == "academy_student_card_image"
    assert decision.confidence == 0.88
    assert decision.evidence == ("학생 카드 요청",)
