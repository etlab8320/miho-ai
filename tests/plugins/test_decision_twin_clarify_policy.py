"""Regression tests for decision-twin clarification policy."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.decision_twin import _decision_twin_pre_gateway_dispatch


def _event(text: str, *, channel_context: str = "") -> MessageEvent:
    event = MessageEvent(
        text=text,
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="u1",
            chat_id="channel-1",
            guild_id="guild-1",
        ),
    )
    event.channel_context = channel_context
    return event


def _gateway() -> SimpleNamespace:
    return SimpleNamespace(_is_user_authorized=lambda _source: True)


@pytest.mark.asyncio
async def test_decision_twin_does_not_clarify_actionable_hakjong_report_request() -> None:
    async def resolver(_messages):
        return {
            "action": "clarify",
            "intent": "유가은 학생의 학종 리포트 생성",
            "confidence": 0.9,
            "user_message": "PDF 생성 경로를 먼저 알려줘.",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("가은이 국민대 경희대 인하대 학교 학종 리포트로 줘"),
        gateway=_gateway(),
        resolver=resolver,
        owner_context_builder=lambda _text: (
            "현재 스레드는 유가은 학생 생기부와 국민대/경희대/인하대 학종 프로필을 이미 확인했다."
        ),
    )

    assert result == {"action": "allow"}


@pytest.mark.asyncio
async def test_decision_twin_does_not_clarify_hakjong_followup_with_thread_context() -> None:
    async def resolver(_messages):
        return {
            "action": "clarify",
            "intent": "3개 대학 리포트 생성 여부 확인",
            "confidence": 0.86,
            "user_message": "텍스트 리포트로 먼저 받을지 PDF로 받을지 정해줘.",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("그러면 3개만 만들어주면되자나"),
        gateway=_gateway(),
        resolver=resolver,
        owner_context_builder=lambda _text: (
            "직전 요청: 유가은 학생 국민대, 경희대, 인하대 학종 프리미엄 PDF 리포트 생성. "
            "중앙대는 프로필 없음."
        ),
    )

    assert result == {"action": "allow"}


@pytest.mark.asyncio
async def test_decision_twin_does_not_clarify_media_redelivery_when_file_context_exists() -> None:
    async def resolver(_messages):
        return {
            "action": "clarify",
            "intent": "이전 PDF 파일 재전달",
            "confidence": 0.92,
            "user_message": "어떤 파일을 말하는지 경로를 알려줘.",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event(
            "방금 만든 PDF 다시 보내줘",
            channel_context="assistant: MEDIA:/Users/etlab/.miho/media_cache/reports/ugaeun_hakjong.pdf",
        ),
        gateway=_gateway(),
        resolver=resolver,
    )

    assert result == {"action": "allow"}


@pytest.mark.asyncio
async def test_decision_twin_does_not_clarify_actionable_life_record_lookup() -> None:
    async def resolver(_messages):
        return {
            "action": "clarify",
            "intent": "학생 생기부 핵심 요약",
            "confidence": 0.88,
            "user_message": "어느 학생의 생기부인지 알려줘.",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("가은이 생기부 핵심만 다시 정리해줘"),
        gateway=_gateway(),
        resolver=resolver,
        owner_context_builder=lambda _text: "현재 스레드에 유가은 학생 생기부 DB가 있다.",
    )

    assert result == {"action": "allow"}


@pytest.mark.asyncio
async def test_decision_twin_blocks_life_record_lock_for_actionable_silgi_recommendation() -> None:
    async def resolver(_messages):
        return {
            "action": "route",
            "route": "life_record",
            "intent": "종환 학생 생기부 확인",
            "required_tool": "life_record_lookup",
            "confidence": 0.92,
            "evidence": ["생기부 성적보고라는 표현이 있다"],
            "tool_instruction": "생기부를 조회한다",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event(
            "종환이 생기부 성적보고 충청 대전 강원권에서 "
            "유리한 학교들 선별해서 상향 2개 4개정도 적정 추려서 줘 실기전형이다"
        ),
        gateway=_gateway(),
        resolver=resolver,
        owner_context_builder=lambda _text: (
            "수시 실기 추천은 학생 성적과 대학별 전형자료를 대조해서 상향/적정 후보를 계산해야 한다."
        ),
    )

    assert result == {"action": "allow"}


@pytest.mark.asyncio
async def test_decision_twin_keeps_clarify_for_actionless_hakjong_request() -> None:
    async def resolver(_messages):
        return {
            "action": "clarify",
            "intent": "학종 리포트 대상 확인",
            "confidence": 0.88,
            "user_message": "어느 학생과 어느 대학 기준인지 알려줘.",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("학종 리포트 만들어줘"),
        gateway=_gateway(),
        resolver=resolver,
    )

    assert result["action"] == "respond"
    assert result["text"] == "어느 학생과 어느 대학 기준인지 알려줘."
