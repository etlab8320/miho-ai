"""Tests for the PACA/Peak academy operations plugin."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from miho_cli.plugins import PluginContext, PluginManager, PluginManifest
from plugins.academy_ops import _academy_command, _capture_gateway_context, _catalog_tool_handler, register
from plugins.academy_ops.auth_flow import AcademyLoginResult, complete_login, create_login_link
from plugins.academy_ops.auth_pages import render_login_page
from plugins.academy_ops.auth_store import decrypt_token, get_binding, key_path
from plugins.academy_ops.catalog import all_operations, find_operation, operations_payload
from plugins.academy_ops.intent import draft_intent
from plugins.academy_ops.paca_client import AcademyLoginError, login_paca
from plugins.academy_ops.server import AcademyAuthHandler
from plugins.academy_ops.trigger import detect_academy_trigger
import plugins.academy_ops as academy_ops_module
import plugins.academy_ops.discord_button as discord_button_module
import plugins.academy_ops.server as auth_server_module


def test_catalog_uses_existing_backend_apis_by_default():
    payload = operations_payload()

    assert payload["api_policy"] == "1차 범위는 기존 PACA/Peak API를 사용한다."
    assert all(not op["needs_new_backend_api"] for op in payload["operations"])


def test_write_operations_require_confirmation_and_audit_log():
    writes = [op for op in all_operations() if op.mode == "write"]

    assert writes
    assert all(op.requires_confirmation for op in writes)
    assert all(op.requires_audit_log for op in writes)


def test_payment_completion_maps_to_existing_paca_payment_endpoint():
    draft = draft_intent("홍길동 학원비 카드 결제 납부 완료")
    op = draft.operation

    assert draft.operation_key == "payment.mark_paid"
    assert draft.needs_confirmation is True
    assert op is not None
    assert op.endpoint.service == "paca"
    assert op.endpoint.method == "POST"
    assert op.endpoint.path == "/paca/payments/{payment_id}/pay"


def test_plan_lookup_maps_to_peak_plans_endpoint():
    draft = draft_intent("5월 25일 박성준 강사 운동계획 보여줘")
    op = draft.operation

    assert draft.operation_key == "plan.by_date"
    assert draft.needs_confirmation is False
    assert op is not None
    assert op.endpoint.service == "peak"
    assert op.endpoint.path == "/peak/plans"


def test_consultation_candidates_are_read_only_composed_analysis():
    op = find_operation("consultation.candidates")

    assert op is not None
    assert op.mode == "read"
    assert op.endpoint.service == "paca+peak"
    assert op.requires_confirmation is False


def test_academy_slash_command_returns_catalog_without_args():
    output = _academy_command("")

    assert "PACA/Peak 디스코드 운영 기능" in output
    assert "새 PACA/Peak API" in output
    assert "확인 버튼" in output


def test_academy_slash_command_previews_write_request():
    output = _academy_command("홍길동 학원비 카드 결제 납부 완료")

    assert "학원비 납부 완료 반영" in output
    assert "디스코드 버튼 승인 필요" in output
    assert "새 API 필요: 아니오" in output


def test_catalog_tool_returns_json_payload():
    payload = json.loads(_catalog_tool_handler({}))

    assert "operations" in payload
    assert any(op["key"] == "attendance.student_month" for op in payload["operations"])


def test_catalog_tool_accepts_dispatch_metadata_kwargs():
    payload = json.loads(_catalog_tool_handler({}, task_id="tool-call-1"))

    assert "operations" in payload


def test_plugin_registers_command_and_tool():
    manager = PluginManager()
    manifest = PluginManifest(name="academy_ops", source="bundled", key="academy_ops")
    ctx = PluginContext(manifest, manager)

    register(ctx)

    assert "academy" in manager._plugin_commands
    assert "academy_operations_catalog" in manager._plugin_tool_names


def test_login_link_uses_public_base_url_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setenv("MIHO_ACADEMY_AUTH_BASE_URL", "https://miho.etlab.kr")

    link = create_login_link(discord_user_id="42", guild_id="7", channel_id="9", now=100)

    assert link.url.startswith("https://miho.etlab.kr/academy/login?state=")
    assert "42" not in link.url
    assert link.expires_at == 100 + 600


def test_gateway_context_enables_academy_login_command(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setenv("MIHO_ACADEMY_AUTH_BASE_URL", "https://miho.etlab.kr")
    event = MessageEvent(
        text="/academy login",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-1",
            chat_id="channel-1",
            guild_id="guild-1",
        ),
    )

    assert _capture_gateway_context(event)["action"] == "allow"
    output = _academy_command("login")

    assert "학원 계정 연결 링크" in output
    assert "https://miho.etlab.kr/academy/login?state=" in output
    assert "로컬 개발용" not in output


def test_login_command_warns_when_only_local_link_available(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.delenv("MIHO_ACADEMY_AUTH_BASE_URL", raising=False)
    event = MessageEvent(
        text="/academy login",
        source=SessionSource(platform=Platform.DISCORD, user_id="u1", chat_id="c1"),
    )

    _capture_gateway_context(event)
    output = _academy_command("login")

    assert "http://127.0.0.1:8765/academy/login?state=" in output
    assert "다른 기기에서는 안 열릴 수 있어" in output


def test_academy_trigger_detects_varied_natural_language():
    samples = [
        "학원관리",
        "파카랑 피크 붙여줘",
        "출석조회 하고 싶은데",
        "학생 관리 좀 보자",
    ]

    assert all(detect_academy_trigger(sample).should_prompt for sample in samples)
    assert not detect_academy_trigger("오늘 날씨 어때?").should_prompt
    assert not detect_academy_trigger("/academy login").should_prompt


@pytest.mark.asyncio
async def test_natural_trigger_sends_discord_login_button(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setenv("MIHO_ACADEMY_AUTH_BASE_URL", "https://academy-login.etlab.kr")

    calls = []

    async def fake_send_discord_link_button(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(academy_ops_module, "send_discord_link_button", fake_send_discord_link_button)
    adapter = SimpleNamespace()
    event = MessageEvent(
        text="학원관리",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-5",
            chat_id="channel-5",
            guild_id="guild-5",
        ),
    )
    gateway = SimpleNamespace(
        adapters={Platform.DISCORD: adapter},
        _is_user_authorized=lambda _source: True,
    )

    result = _capture_gateway_context(event, gateway=gateway)
    await asyncio.sleep(0)

    assert result == {"action": "skip", "reason": "academy_ops_login_button"}
    assert calls
    assert calls[0]["button_label"] == "학원 계정 연결하기"
    assert calls[0]["url"].startswith("https://academy-login.etlab.kr/academy/login?state=")
    assert "PACA랑 Peak은 같은 로그인 토큰" in calls[0]["content"]


def test_natural_trigger_does_not_bypass_gateway_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    event = MessageEvent(
        text="파카 연동해줘",
        source=SessionSource(platform=Platform.DISCORD, user_id="bad-user", chat_id="channel-5"),
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: False)

    assert _capture_gateway_context(event, gateway=gateway) == {"action": "allow"}


@pytest.mark.asyncio
async def test_discord_button_sender_renders_url_button(monkeypatch):
    from plugins.platforms.discord import adapter as discord_adapter

    class FakeView:
        def __init__(self, **_kwargs):
            self.children = []

        def add_item(self, item):
            self.children.append(item)

    class FakeButton:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    fake_discord = SimpleNamespace(
        Embed=lambda **kwargs: SimpleNamespace(**kwargs),
        Color=SimpleNamespace(blue=lambda: 3),
        ui=SimpleNamespace(View=FakeView, Button=FakeButton),
        ButtonStyle=SimpleNamespace(link=5),
    )
    sent_message = SimpleNamespace(id=991)
    channel = SimpleNamespace(send=AsyncMock(return_value=sent_message))
    adapter = SimpleNamespace(
        _client=SimpleNamespace(get_channel=lambda _id: channel, fetch_channel=AsyncMock())
    )
    monkeypatch.setattr(discord_adapter, "DISCORD_AVAILABLE", True)
    monkeypatch.setattr(discord_adapter, "discord", fake_discord)
    monkeypatch.setattr(discord_button_module, "is_safe_url", lambda _url: True)

    ok = await discord_button_module.send_discord_link_button(
        adapter=adapter,
        chat_id="123",
        content="학원관리 연결부터 할게.",
        button_label="학원 계정 연결하기",
        url="https://academy-login.etlab.kr/academy/login?state=abc",
        title="PACA/Peak 학원관리 연결",
    )

    assert ok is True
    kwargs = channel.send.await_args.kwargs
    assert kwargs["embed"].title == "PACA/Peak 학원관리 연결"
    assert kwargs["view"].children[0].label == "학원 계정 연결하기"
    assert kwargs["view"].children[0].url.startswith("https://academy-login.etlab.kr/")


def test_complete_login_encrypts_token_and_binds_discord_user(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    link = create_login_link(discord_user_id="discord-user-2", now=100)

    binding = complete_login(
        link.state,
        AcademyLoginResult(
            token="paca-secret-token",
            user_id="11",
            email="teacher@example.com",
            name="박성준",
            role="admin",
            academy_id="3",
            academy_name="맥스체대입시",
        ),
        now=120,
    )

    stored = get_binding("discord-user-2")
    assert stored == binding
    assert stored is not None
    assert stored.token_ciphertext != "paca-secret-token"
    assert decrypt_token(stored.token_ciphertext) == "paca-secret-token"
    assert "paca-secret-token" not in (tmp_path / "academy_ops" / "bindings.json").read_text()
    if os.name != "nt":
        mode = stat.S_IMODE(key_path().stat().st_mode)
        assert mode == 0o600


def test_login_page_escapes_state_and_error():
    html = render_login_page(state='bad"><script>', error="<실패>")

    assert 'bad&quot;&gt;&lt;script&gt;' in html
    assert "&lt;실패&gt;" in html
    assert "<script>" not in html


def test_paca_login_client_parses_success_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/paca/auth/login"
        return httpx.Response(
            200,
            json={
                "token": "token-123",
                "user": {
                    "id": 7,
                    "email": "coach@example.com",
                    "name": "박성준",
                    "role": "admin",
                    "academyId": 3,
                    "academy": {"name": "맥스체대입시"},
                },
            },
        )

    result = login_paca(
        email="coach@example.com",
        password="secret",
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )

    assert result.token == "token-123"
    assert result.academy_id == "3"
    assert result.academy_name == "맥스체대입시"


def test_paca_login_client_returns_plain_korean_error_on_unauthorized():
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={"message": "no"}))

    try:
        login_paca(
            email="bad@example.com",
            password="wrong",
            base_url="https://example.test",
            transport=transport,
        )
    except AcademyLoginError as exc:
        assert str(exc) == "이메일이나 비밀번호가 맞지 않아."
    else:
        raise AssertionError("expected AcademyLoginError")


def test_auth_server_serves_mobile_login_page(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    link = create_login_link(discord_user_id="discord-user-3", now=100)
    server = ThreadingHTTPServer(("127.0.0.1", 0), AcademyAuthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        port = server.server_address[1]
        state = urllib.parse.quote(link.state)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/academy/login?state={state}",
            timeout=5,
        ) as response:
            body = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()

    assert "Miho 학원 계정 연결" in body
    assert "viewport" in body
    assert "min-height: 48px" in body


def test_auth_server_suppresses_favicon_noise():
    server = ThreadingHTTPServer(("127.0.0.1", 0), AcademyAuthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        port = server.server_address[1]
        request = urllib.request.Request(f"http://127.0.0.1:{port}/favicon.ico")
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status
            body = response.read()
    finally:
        server.shutdown()
        server.server_close()

    assert status == 204
    assert body == b""


def test_auth_server_rate_limits_repeated_login_failures(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    def fail_login(**_: object) -> AcademyLoginResult:
        raise AcademyLoginError("이메일이나 비밀번호가 맞지 않아.")

    monkeypatch.setattr(auth_server_module, "login_paca", fail_login)
    link = create_login_link(discord_user_id="discord-user-4", now=100)
    server = ThreadingHTTPServer(("127.0.0.1", 0), AcademyAuthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/academy/login"
        payload = urllib.parse.urlencode(
            {"state": link.state, "email": "bad@example.com", "password": "wrong"}
        ).encode("utf-8")
        for _ in range(8):
            request = urllib.request.Request(url, data=payload, method="POST")
            try:
                urllib.request.urlopen(request, timeout=5)
            except urllib.error.HTTPError as exc:
                assert exc.code == 401
                exc.read()
        request = urllib.request.Request(url, data=payload, method="POST")
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read().decode("utf-8")
        else:
            raise AssertionError("expected rate limit response")
    finally:
        server.shutdown()
        server.server_close()

    assert status == 429
    assert "로그인 시도가 너무 많아" in body
