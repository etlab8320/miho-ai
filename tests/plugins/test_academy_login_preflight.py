"""Tests for natural-language PACA/Peak login routing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.academy_ops import _academy_pre_gateway_dispatch
from plugins.academy_ops.auth_flow import load_pending_logins
from plugins.academy_ops.login_preflight import is_academy_login_request


def test_academy_login_request_detection_is_intent_based() -> None:
    assert is_academy_login_request("파카로그인 하자")
    assert is_academy_login_request("피크 계정 연결해줘")
    assert is_academy_login_request("학원관리 로그인 연결해줘")
    assert not is_academy_login_request("로그인 했어")
    assert not is_academy_login_request("학생 카드 디자인 의견 줘")


@pytest.mark.asyncio
async def test_natural_login_request_returns_login_link_for_authorized_discord_user(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setenv("MIHO_ACADEMY_AUTH_BASE_URL", "https://academy-login.etlab.kr")
    event = MessageEvent(
        text="파카 로그인 하자",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-1",
            chat_id="channel-1",
            guild_id="guild-1",
        ),
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: True)

    result = await _academy_pre_gateway_dispatch(event, gateway=gateway)

    assert result["action"] == "respond"
    assert "https://academy-login.etlab.kr/academy/login?state=" in result["text"]
    pending = load_pending_logins()
    assert len(pending) == 1
    assert next(iter(pending.values())).discord_user_id == "discord-user-1"


@pytest.mark.asyncio
async def test_natural_login_request_does_not_bypass_gateway_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    event = MessageEvent(
        text="학원관리 로그인 연결해줘",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="bad-user",
            chat_id="channel-1",
            guild_id="guild-1",
        ),
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: False)

    assert await _academy_pre_gateway_dispatch(event, gateway=gateway) == {"action": "allow"}
    assert load_pending_logins() == {}
