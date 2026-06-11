"""Gateway pre-dispatch response hook tests."""

from __future__ import annotations

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.run import GatewayRunner
from gateway.session import SessionSource


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_respond_returns_plugin_text(monkeypatch) -> None:
    async def fake_invoke_hook_async(*_: object, **__: object) -> list[dict[str, str]]:
        return [{"action": "respond", "text": "빠른 응답"}]

    monkeypatch.setattr("miho_cli.plugins.invoke_hook_async", fake_invoke_hook_async)
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.session_store = object()
    event = MessageEvent(
        text="5월 학원일정 줘",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="u1",
            chat_id="c1",
        ),
    )

    assert await runner._handle_message(event) == "빠른 응답"


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_allow_does_not_mask_later_response(monkeypatch) -> None:
    async def fake_invoke_hook_async(*_: object, **__: object) -> list[dict[str, str]]:
        return [{"action": "allow"}, {"action": "respond", "text": "뒤 플러그인 응답"}]

    monkeypatch.setattr("miho_cli.plugins.invoke_hook_async", fake_invoke_hook_async)
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.session_store = object()
    event = MessageEvent(
        text="https://www.youtube.com/watch?v=Ghj69GLDiqI 정리해줘",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="u1",
            chat_id="c1",
        ),
    )

    assert await runner._handle_message(event) == "뒤 플러그인 응답"


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_uses_highest_priority_response(monkeypatch) -> None:
    async def fake_invoke_hook_async(*_: object, **__: object) -> list[dict[str, object]]:
        return [
            {"action": "respond", "text": "낮은 우선순위", "route": "generic", "priority": 0},
            {"action": "respond", "text": "높은 우선순위", "route": "life_record", "priority": 100},
        ]

    monkeypatch.setattr("miho_cli.plugins.invoke_hook_async", fake_invoke_hook_async)
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.session_store = object()
    event = MessageEvent(
        text="생기부 저장해줘",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="u1",
            chat_id="c1",
        ),
    )

    assert await runner._handle_message(event) == "높은 우선순위"
