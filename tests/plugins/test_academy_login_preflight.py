"""Tests for natural-language PACA/Peak login routing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.academy_ops import _academy_pre_gateway_dispatch
from plugins.academy_ops.auth_flow import load_pending_logins
from plugins.academy_ops.auth_store import AcademyBinding, encrypt_token, save_binding
from plugins.academy_ops.login_preflight import is_academy_login_request, is_academy_login_status_request


def test_academy_login_request_detection_is_intent_based() -> None:
    assert is_academy_login_request("파카로그인 하자")
    assert is_academy_login_request("피크 계정 연결해줘")
    assert is_academy_login_request("학원관리 로그인 연결해줘")
    assert not is_academy_login_request("로그인 했어")
    assert is_academy_login_status_request("로그인했어 되었는지 확인해줘")
    assert is_academy_login_status_request("로그인 완료")
    assert not is_academy_login_request("학생 카드 디자인 의견 줘")
    assert not is_academy_login_status_request("학생 카드 디자인 의견 줘")


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
async def test_natural_login_request_accepts_string_discord_platform(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    event = MessageEvent(
        text="피크 계정 연결해줘",
        source=SimpleNamespace(
            platform="discord",
            user_id="discord-user-2",
            chat_id="channel-1",
            guild_id="guild-1",
            parent_chat_id="",
            parent_chat_name="",
            chat_name="",
        ),
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: True)

    result = await _academy_pre_gateway_dispatch(event, gateway=gateway)

    assert result["action"] == "respond"
    assert "/academy/login?state=" in result["text"]


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


@pytest.mark.asyncio
async def test_login_completion_confirmation_returns_binding_status(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr("plugins.academy_ops.refresh_remote_pending_logins", lambda: 0)
    save_binding(
        AcademyBinding(
            discord_user_id="discord-user-1",
            user_id="academy-user-1",
            email="owner@example.com",
            name="정으뜸",
            role="owner",
            academy_id="academy-1",
            academy_name="일산 맥스체대입시",
            token_ciphertext=encrypt_token("token"),
            created_at=1,
            updated_at=1,
        )
    )
    event = MessageEvent(
        text="로그인했어 되었는지 확인해줘",
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
    assert "연결됨" in result["text"]
    assert "정으뜸" in result["text"]


@pytest.mark.asyncio
async def test_login_completion_confirmation_reports_missing_binding(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr("plugins.academy_ops.refresh_remote_pending_logins", lambda: 0)
    event = MessageEvent(
        text="로그인 완료 확인해줘",
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
    assert "아직 학원 계정이 연결되지 않았어" in result["text"]
