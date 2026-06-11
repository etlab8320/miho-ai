"""Tests for natural-language PACA/Peak login routing."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.academy_ops import _academy_pre_gateway_dispatch
from plugins.academy_ops.auth_flow import create_login_link, load_pending_logins
from plugins.academy_ops.auth_gate import academy_request_needs_login
from plugins.academy_ops.auth_store import AcademyBinding, encrypt_token, save_binding
from plugins.academy_ops.login_preflight import is_academy_login_request, is_academy_login_status_request


@pytest.fixture
def _semantic_login_request(monkeypatch):
    """Patch semantic_intents to classify as login_request."""
    from plugins.academy_ops import login_preflight

    login_preflight._last_login.update(text=None, label=None, hit=False)
    monkeypatch.setattr(
        "plugins.academy_ops.login_preflight.semantic_intents.classify",
        lambda text, group, intents, **kwargs: "login_request",
    )
    yield
    login_preflight._last_login.update(text=None, label=None, hit=False)


@pytest.fixture
def _semantic_login_status(monkeypatch):
    """Patch semantic_intents to classify as login_status."""
    from plugins.academy_ops import login_preflight

    login_preflight._last_login.update(text=None, label=None, hit=False)
    monkeypatch.setattr(
        "plugins.academy_ops.login_preflight.semantic_intents.classify",
        lambda text, group, intents, **kwargs: "login_status",
    )
    yield
    login_preflight._last_login.update(text=None, label=None, hit=False)


@pytest.fixture
def _semantic_abstain(monkeypatch):
    """Patch semantic_intents to abstain (return None) — no embedding provider."""
    from plugins.academy_ops import login_preflight

    login_preflight._last_login.update(text=None, label=None, hit=False)
    monkeypatch.setattr(
        "plugins.academy_ops.login_preflight.semantic_intents.classify",
        lambda text, group, intents, **kwargs: None,
    )
    yield
    login_preflight._last_login.update(text=None, label=None, hit=False)


def test_academy_login_request_detection_is_intent_based() -> None:
    """semantic_intents가 label을 반환하면 그 값을 그대로 사용한다."""
    from plugins.academy_ops import login_preflight

    login_preflight._last_login.update(text=None, label=None, hit=False)
    original_classify = login_preflight.semantic_intents.classify

    # login_request 반환 시
    login_preflight.semantic_intents.classify = lambda text, group, intents, **kw: "login_request"
    login_preflight._last_login.update(text=None, label=None, hit=False)
    assert is_academy_login_request("파카로그인 하자")
    assert not is_academy_login_status_request("파카로그인 하자")

    # login_status 반환 시
    login_preflight._last_login.update(text=None, label=None, hit=False)
    login_preflight.semantic_intents.classify = lambda text, group, intents, **kw: "login_status"
    login_preflight._last_login.update(text=None, label=None, hit=False)
    assert is_academy_login_status_request("로그인했어 되었는지 확인해줘")
    assert not is_academy_login_request("로그인했어 되었는지 확인해줘")

    # none 반환 시
    login_preflight._last_login.update(text=None, label=None, hit=False)
    login_preflight.semantic_intents.classify = lambda text, group, intents, **kw: "none"
    login_preflight._last_login.update(text=None, label=None, hit=False)
    assert not is_academy_login_request("학생 카드 디자인 의견 줘")
    assert not is_academy_login_status_request("학생 카드 디자인 의견 줘")

    login_preflight.semantic_intents.classify = original_classify
    login_preflight._last_login.update(text=None, label=None, hit=False)


def test_keyword_fallback_absent_when_semantic_abstains(_semantic_abstain) -> None:
    """semantic이 None을 반환(abstain)하면 키워드 폴백 없이 False를 반환한다."""
    # 예전 키워드 경로에서는 True였을 입력들
    assert not is_academy_login_request("파카로그인 하자")
    assert not is_academy_login_request("피크 계정 연결해줘")
    assert not is_academy_login_status_request("로그인했어 되었는지 확인해줘")
    assert not is_academy_login_status_request("파카 로그인되어있어?")


@pytest.mark.asyncio
async def test_academy_domain_request_without_binding_returns_login_before_body_agent(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setenv("MIHO_ACADEMY_AUTH_BASE_URL", "https://academy-login.etlab.kr")
    monkeypatch.setattr("plugins.academy_ops.gateway_dispatch.refresh_remote_pending_logins", lambda: 0)

    async def needs_login(*_: object, **__: object) -> bool:
        return True

    async def fail_if_real_tool_router_runs(*_: object, **__: object) -> object:
        raise AssertionError("unauthenticated academy request must not reach tool execution")

    monkeypatch.setattr("plugins.academy_ops.gateway_dispatch.academy_request_needs_login", needs_login)
    monkeypatch.setattr(
        "plugins.academy_ops.gateway_dispatch.resolve_and_execute_academy_request",
        fail_if_real_tool_router_runs,
    )
    event = MessageEvent(
        text="현재 재원생들 남여 따로 제멀 최든기록 평균이 어느정도야?",
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
    assert len(load_pending_logins()) == 1


@pytest.mark.asyncio
async def test_non_academy_request_without_binding_still_allows_body_agent(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr("plugins.academy_ops.gateway_dispatch.refresh_remote_pending_logins", lambda: 0)

    async def does_not_need_login(*_: object, **__: object) -> bool:
        return False

    monkeypatch.setattr("plugins.academy_ops.gateway_dispatch.academy_request_needs_login", does_not_need_login)
    event = MessageEvent(
        text="오늘 날씨 보고 운동복 뭐 입을지 알려줘",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-1",
            chat_id="channel-1",
            guild_id="guild-1",
        ),
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: True)

    assert await _academy_pre_gateway_dispatch(event, gateway=gateway) == {"action": "allow"}
    assert load_pending_logins() == {}


@pytest.mark.asyncio
async def test_expired_binding_academy_domain_request_returns_login_before_tools(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setenv("MIHO_ACADEMY_AUTH_BASE_URL", "https://academy-login.etlab.kr")
    monkeypatch.setattr("plugins.academy_ops.gateway_dispatch.refresh_remote_pending_logins", lambda: 0)
    save_binding(
        AcademyBinding(
            discord_user_id="discord-user-1",
            user_id="academy-user-1",
            email="owner@example.com",
            name="정으뜸",
            role="owner",
            academy_id="3",
            academy_name="학원",
            token_ciphertext=encrypt_token("expired-token"),
            token_expires_at=1,
            created_at=1,
            updated_at=1,
        )
    )

    async def needs_login(*_: object, **__: object) -> bool:
        return True

    async def fail_if_real_tool_router_runs(*_: object, **__: object) -> object:
        raise AssertionError("expired token must be blocked before tool execution")

    monkeypatch.setattr("plugins.academy_ops.gateway_dispatch.academy_request_needs_login", needs_login)
    monkeypatch.setattr(
        "plugins.academy_ops.gateway_dispatch.resolve_and_execute_academy_request",
        fail_if_real_tool_router_runs,
    )
    event = MessageEvent(
        text="강남 박서현 최근 기록 보여줘",
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
    assert len(load_pending_logins()) == 1


@pytest.mark.asyncio
async def test_academy_mismatch_binding_returns_reconnect_login_link(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setenv("MIHO_ACADEMY_AUTH_BASE_URL", "https://academy-login.etlab.kr")
    monkeypatch.setattr("plugins.academy_ops.gateway_dispatch.refresh_remote_pending_logins", lambda: 0)
    save_binding(
        AcademyBinding(
            discord_user_id="discord-user-1",
            user_id="academy-user-1",
            email="owner@example.com",
            name="정으뜸",
            role="owner",
            academy_id="3",
            academy_name="학원",
            token_ciphertext=encrypt_token(_jwt({"academyId": 9, "exp": 1_800_000_000})),
            token_expires_at=1_800_000_000,
            created_at=1,
            updated_at=1,
        )
    )

    async def needs_login(*_: object, **__: object) -> bool:
        return True

    monkeypatch.setattr("plugins.academy_ops.gateway_dispatch.academy_request_needs_login", needs_login)
    event = MessageEvent(
        text="강남 박서현 최근 기록 보여줘",
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
    assert "https://academy-login.etlab.kr" in result["text"]
    assert "/academy/login?state=" in result["text"]
    assert "관리자에게 문의" not in result["text"]
    assert result["route"] == "academy_ops"
    assert result["reason"] == "login_reconnect"
    assert load_pending_logins()


@pytest.mark.asyncio
async def test_auth_gate_detects_academy_execute_decision_without_running_real_tool() -> None:
    async def resolver(_messages: list[dict[str, str]]) -> object:
        return _response(
            {
                "action": "execute",
                "domain": "academy_ops",
                "tool": "academy_student_record_lookup",
                "confidence": 0.92,
                "intent": {"kind": "student_record_lookup"},
                "evidence": ["최근 기록"],
                "args": {"student_query": "박서현"},
            }
        )

    assert await academy_request_needs_login("박서현 최근 기록 보여줘", resolver=resolver)


@pytest.mark.asyncio
async def test_auth_gate_allows_non_academy_decision() -> None:
    async def resolver(_messages: list[dict[str, str]]) -> object:
        return _response(
            {
                "action": "allow",
                "domain": "general",
                "confidence": 0.95,
                "intent": {"kind": "weather"},
                "evidence": ["날씨"],
            }
        )

    assert not await academy_request_needs_login("오늘 날씨 알려줘", resolver=resolver)


@pytest.mark.asyncio
async def test_natural_login_request_returns_login_link_for_authorized_discord_user(
    monkeypatch,
    tmp_path,
    _semantic_login_request,
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
async def test_natural_login_request_accepts_string_discord_platform(
    monkeypatch,
    tmp_path,
    _semantic_login_request,
) -> None:
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
async def test_natural_login_request_does_not_bypass_gateway_auth(
    monkeypatch,
    tmp_path,
    _semantic_login_request,
) -> None:
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
async def test_login_completion_confirmation_returns_binding_status(
    monkeypatch,
    tmp_path,
    _semantic_login_status,
) -> None:
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
async def test_login_completion_confirmation_reports_missing_binding(
    monkeypatch,
    tmp_path,
    _semantic_login_status,
) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr("plugins.academy_ops.refresh_remote_pending_logins", lambda: 0)
    event = MessageEvent(
        text="파카 로그인 완료 확인해줘",
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


@pytest.mark.asyncio
async def test_generic_login_confirmation_without_academy_context_is_ignored(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr("plugins.academy_ops.refresh_remote_pending_logins", lambda: 0)
    # semantic이 None(abstain) 반환 → override 없음 → allow
    from plugins.academy_ops import login_preflight
    login_preflight._last_login.update(text=None, label=None, hit=False)
    monkeypatch.setattr(
        "plugins.academy_ops.login_preflight.semantic_intents.classify",
        lambda text, group, intents, **kwargs: None,
    )
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

    assert await _academy_pre_gateway_dispatch(event, gateway=gateway) == {"action": "allow"}


@pytest.mark.asyncio
async def test_pending_login_allows_generic_completion_confirmation(
    monkeypatch,
    tmp_path,
    _semantic_login_status,
) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr("plugins.academy_ops.refresh_remote_pending_logins", lambda: 0)
    create_login_link(discord_user_id="discord-user-1", guild_id="guild-1", channel_id="channel-1")
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
    assert len(load_pending_logins()) == 1


@pytest.mark.asyncio
async def test_academy_login_status_question_does_not_create_link(
    monkeypatch,
    tmp_path,
    _semantic_login_status,
) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr("plugins.academy_ops.refresh_remote_pending_logins", lambda: 0)
    event = MessageEvent(
        text="파카 로그인되어있어?",
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
    assert load_pending_logins() == {}


def _jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}
    return ".".join((_b64(header), _b64(payload), "signature"))


def _b64(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _response(payload: dict[str, object]) -> SimpleNamespace:
    content = json.dumps(payload, ensure_ascii=False)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
