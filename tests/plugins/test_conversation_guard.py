from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugins.conversation_guard import (
    _guard_pre_gateway_dispatch,
    is_low_information_message,
)


@pytest.mark.parametrize("text", ["ㅎㅜㅑㅔ", "ㅋㅋ", "???", "ㅠㅠ", "ㄴㄴ"])
def test_low_information_message_is_blocked(text: str) -> None:
    assert is_low_information_message(text)


@pytest.mark.parametrize(
    "text",
    [
        "응",
        "ㄱㄱ",
        "/academy login",
        "김보민 기록 보여줘",
        "현재 재원생 몇 명이야?",
        "ET-SMOKE-003 상태 알려줘",
    ],
)
def test_normal_message_is_allowed(text: str) -> None:
    assert not is_low_information_message(text)


@pytest.mark.asyncio
async def test_guard_responds_with_plain_korean_clarification() -> None:
    result = await _guard_pre_gateway_dispatch(event=SimpleNamespace(text="ㅎㅜㅑㅔ"))

    assert result["action"] == "respond"
    assert "다시 말해" in result["text"]
    assert "400" not in result["text"]
    assert "CORS" not in result["text"]
    assert "오류" not in result["text"]


@pytest.mark.asyncio
async def test_guard_allows_meaningful_turn() -> None:
    result = await _guard_pre_gateway_dispatch(event=SimpleNamespace(text="김보민 기록 보여줘"))

    assert result == {"action": "allow"}


@pytest.mark.asyncio
async def test_guard_allows_low_information_turn_with_context() -> None:
    result = await _guard_pre_gateway_dispatch(
        event=SimpleNamespace(
            text="???",
            media_urls=["/tmp/report.pdf"],
            channel_context="앞에서 자료를 보내 달라고 했다.",
        )
    )

    assert result == {"action": "allow"}
