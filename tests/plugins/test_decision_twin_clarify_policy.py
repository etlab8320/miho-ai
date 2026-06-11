"""Regression tests for decision-twin clarification policy.

clarify 액션은 무조건 allow로 처리된다 (domain_guard / should_skip_clarify_response 제거 후).
"""

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
async def test_clarify_always_returns_allow() -> None:
    """LLM이 clarify를 반환하면 무조건 allow다."""

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
async def test_clarify_returns_allow_for_hakjong_followup() -> None:
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
async def test_clarify_returns_allow_for_media_redelivery() -> None:
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
async def test_clarify_returns_allow_for_life_record_lookup() -> None:
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
async def test_clarify_returns_allow_for_silgi_recommendation() -> None:
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

    # route + required_tool + confidence >= 0.72 → rewrite (가드 없음)
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

    # domain_guard 없음 — rewrite로 통과, 원문 보존
    assert result["action"] == "rewrite"
    assert "종환이 생기부 성적보고" in result["text"]


@pytest.mark.asyncio
async def test_clarify_returns_allow_for_actionless_request() -> None:
    """clarify는 이제 무조건 allow — respond 분기 없음."""

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

    assert result == {"action": "allow"}
