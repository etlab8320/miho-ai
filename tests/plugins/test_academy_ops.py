"""Tests for the PACA/Peak academy operations plugin."""

from __future__ import annotations

import json
import os
import stat
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

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
from plugins.academy_ops.catalog import CONNECTED_APIS, all_operations, find_operation, operations_payload
from plugins.academy_ops.intent import draft_intent
from plugins.academy_ops.paca_client import AcademyLoginError, login_paca
from plugins.academy_ops.server import AcademyAuthHandler
import plugins.academy_ops as academy_ops_module
import plugins.academy_ops.server as auth_server_module


def test_catalog_separates_connected_api_from_roadmap_candidates():
    payload = operations_payload()

    assert payload["catalog_status"] == "roadmap"
    assert "실제 구현된 API는 로그인 바인딩뿐" in payload["api_policy"]
    assert payload["connected_apis"][0]["key"] == "auth.login"
    assert payload["connected_apis"][0]["implementation_status"] == "implemented"
    assert all(op["implementation_status"] == "planned" for op in payload["operations"])
    assert all(op["api_contract_status"] == "unverified" for op in payload["operations"])


def test_write_operations_require_confirmation_and_audit_log():
    writes = [op for op in all_operations() if op.mode == "write"]

    assert writes
    assert all(op.requires_confirmation for op in writes)
    assert all(op.requires_audit_log for op in writes)


def test_connected_api_is_only_login_binding_for_now():
    assert [op.key for op in CONNECTED_APIS] == ["auth.login"]
    assert CONNECTED_APIS[0].endpoint.path == "/paca/auth/login"


def test_payment_completion_stays_a_planned_write_candidate():
    draft = draft_intent("홍길동 학원비 카드 결제 납부 완료")
    op = draft.operation

    assert draft.operation_key == "payment.mark_paid"
    assert draft.needs_confirmation is True
    assert op is not None
    assert op.implementation_status == "planned"
    assert op.api_contract_status == "unverified"
    assert op.endpoint.path == "backend route inspection required"


def test_plan_lookup_stays_a_planned_read_candidate():
    draft = draft_intent("5월 25일 박성준 강사 운동계획 보여줘")
    op = draft.operation

    assert draft.operation_key == "plan.by_date"
    assert draft.needs_confirmation is False
    assert op is not None
    assert op.implementation_status == "planned"
    assert op.endpoint.path == "backend route inspection required"


def test_consultation_candidates_are_read_only_composed_analysis():
    op = find_operation("consultation.candidates")

    assert op is not None
    assert op.mode == "read"
    assert op.requires_confirmation is False
    assert op.api_contract_status == "unverified"


def test_academy_slash_command_returns_catalog_without_args():
    output = _academy_command("")

    assert "PACA/Peak 디스코드 운영 기능" in output
    assert "현재 실제 연결된 건 PACA/Peak 로그인 바인딩" in output
    assert "연동 후보" in output
    assert "확인 버튼" in output


def test_academy_slash_command_previews_write_request():
    output = _academy_command("홍길동 학원비 카드 결제 납부 완료")

    assert "학원비 납부 완료 반영" in output
    assert "디스코드 버튼 승인 필요" in output
    assert "구현 상태: 연동 후보" in output
    assert "새 API 필요: 백엔드 route 확인 전 판단 불가" in output


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


def test_non_slash_academy_language_is_not_rewritten_to_static_catalog(monkeypatch):
    monkeypatch.setattr(
        academy_ops_module,
        "get_binding",
        lambda _user_id: SimpleNamespace(name="맥스", academy_name="ET", role="owner"),
    )
    event = MessageEvent(
        text=(
            "학생 카드를 만드는것을 해야하는데 의견좀 줘봐. "
            "연결된 api와 비교해서 어떤 부분 api를 연동해야할지 디자인은 어떻게 할지"
        ),
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-5",
            chat_id="channel-5",
            guild_id="guild-5",
        ),
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: True)

    assert _capture_gateway_context(event, gateway=gateway) == {"action": "allow"}


def test_non_slash_academy_language_does_not_bypass_gateway_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    event = MessageEvent(
        text="파카 연동해줘",
        source=SessionSource(platform=Platform.DISCORD, user_id="bad-user", chat_id="channel-5"),
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: False)

    assert _capture_gateway_context(event, gateway=gateway) == {"action": "allow"}


def test_non_slash_login_request_is_left_to_miho_context(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    event = MessageEvent(
        text="학원관리 로그인 연결해줘",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-5",
            chat_id="channel-5",
            guild_id="guild-5",
        ),
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: True)

    assert _capture_gateway_context(event, gateway=gateway) == {"action": "allow"}


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
