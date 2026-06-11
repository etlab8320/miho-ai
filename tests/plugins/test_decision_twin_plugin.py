"""Tests for the LLM-backed Miho decision-twin pre-dispatch plugin."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.decision_twin import _decision_twin_pre_gateway_dispatch
from plugins.decision_twin.router import build_decision_messages, parse_decision_payload


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
