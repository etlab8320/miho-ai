"""Discord gateway command and pre-dispatch handling for academy operations."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .auth_flow import (
    LINK_TTL_SECONDS,
    create_login_link,
    has_pending_login_for_user as has_pending_login,
    refresh_remote_pending_logins,
    resolve_auth_base_url,
)
from .auth_store import delete_binding, get_binding
from .auth_gate import academy_request_needs_login, binding_auth_error
from .context import (
    CHANNEL_ID,
    DISCORD_USER_ID,
    GUILD_ID,
    capture_gateway_context,
    set_gateway_context,
)
from .fast_model_routing import route_bound_academy_session_to_fast_model
from .formatting import format_binding_status, format_catalog, format_login_link
from .guidance_copy import naturalize_guidance_response
from . import login_preflight
from .natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from .self_check import verdict_or_ok
from .thread_context import academy_context_key, format_context_note, get_thread_context


logger = logging.getLogger(__name__)
ACADEMY_ROUTE_PRIORITY = 30


def _academy_command(raw_args: str = "") -> str:
    text = raw_args.strip()
    if not text:
        return format_catalog()
    subcommand, _, remainder = text.partition(" ")
    normalized = subcommand.lower().strip()
    if normalized == "quick":
        return "빠른 문장 가로채기는 꺼져 있어. 일반 문장으로 요청하면 미호가 판단해서 필요한 도구를 호출할게."
    if normalized in {"login", "link"}:
        return _login_command()
    if normalized == "status":
        return _status_command()
    if normalized == "logout":
        return _logout_command()
    return format_catalog()


def _login_command() -> str:
    discord_user_id = DISCORD_USER_ID.get()
    if not discord_user_id:
        return "디스코드 사용자 정보를 확인하지 못했어. 디스코드에서 `/academy login`으로 다시 실행해줘."
    link = create_login_link(
        discord_user_id=discord_user_id,
        guild_id=GUILD_ID.get(),
        channel_id=CHANNEL_ID.get(),
    )
    base_url = resolve_auth_base_url()
    return format_login_link(
        link.url,
        LINK_TTL_SECONDS // 60,
        is_local=base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost"),
    )


def _status_command() -> str:
    discord_user_id = DISCORD_USER_ID.get()
    if not discord_user_id:
        return "디스코드 사용자 정보를 확인하지 못했어."
    refresh_remote_pending_logins()
    binding = get_binding(discord_user_id)
    if binding is None:
        return "아직 학원 계정이 연결되지 않았어. `/academy login`으로 먼저 연결해줘."
    return format_binding_status(binding.name, binding.academy_name, binding.role)


def _logout_command() -> str:
    discord_user_id = DISCORD_USER_ID.get()
    if not discord_user_id:
        return "디스코드 사용자 정보를 확인하지 못했어."
    if delete_binding(discord_user_id):
        return "학원 계정 연결을 해제했어."
    return "연결된 학원 계정이 없었어."


def _capture_gateway_context(event: Any = None, **kwargs: Any) -> dict[str, str]:
    capture_gateway_context(event)
    gateway = kwargs.get("gateway")
    set_gateway_context(gateway)
    discord_user_id = DISCORD_USER_ID.get()
    route_bound_academy_session_to_fast_model(
        gateway=gateway,
        event=event,
        has_binding=bool(discord_user_id and get_binding(discord_user_id)),
    )
    return {"action": "allow"}


async def _academy_pre_gateway_dispatch(event: Any = None, **kwargs: Any) -> dict[str, object]:
    _capture_gateway_context(event, **kwargs)
    source = getattr(event, "source", None)
    platform_raw = getattr(source, "platform", "")
    platform = str(getattr(platform_raw, "value", platform_raw) or "")
    discord_user_id = DISCORD_USER_ID.get()
    if platform != "discord" or not discord_user_id:
        return {"action": "allow"}
    refresh_remote_pending_logins()
    text = str(getattr(event, "text", "") or "")
    binding = get_binding(discord_user_id)
    has_login_context = (
        login_preflight.has_academy_login_context(text) or binding is not None or has_pending_login(discord_user_id)
    )
    if login_preflight.is_academy_login_status_request(text) and has_login_context:
        if login_preflight.is_gateway_source_authorized(kwargs.get("gateway"), source):
            return {
                "action": "respond",
                "text": await _guidance_text(text, "login_status", _status_command()),
                "route": "academy_ops",
                "reason": "login_status",
                "priority": ACADEMY_ROUTE_PRIORITY,
            }
        return {"action": "allow"}
    if login_preflight.is_academy_login_request(text):
        if login_preflight.is_gateway_source_authorized(kwargs.get("gateway"), source):
            return {
                "action": "respond",
                "text": await _guidance_text(text, "login_link", _login_command()),
                "route": "academy_ops",
                "reason": "login_link",
                "priority": ACADEMY_ROUTE_PRIORITY,
            }
        return {"action": "allow"}
    context_key = academy_context_key(event)
    auth_error = binding_auth_error(binding)
    if auth_error:
        if await academy_request_needs_login(text, context_key=context_key):
            if not login_preflight.is_gateway_source_authorized(kwargs.get("gateway"), source):
                return {"action": "allow"}
            if "/academy login" in auth_error:
                fallback = _login_command()
                return _route_response(await _guidance_text(text, "login_required", fallback), "login_required")
            fallback = _login_command()
            return _route_response(await _guidance_text(text, "login_required", fallback), "login_reconnect")
        return {"action": "allow"}
    route = await resolve_and_execute_academy_request(
        text,
        context_key=context_key,
    )
    if route == AcademyNaturalRoute.HANDLED:
        answer = route.response_text
        try:
            verdict = await verdict_or_ok(text, answer)
        except Exception:
            verdict = "ok"
        if verdict != "retry":
            _persist_handled_turn(kwargs.get("session_store"), event, text, answer)
            return _route_response(answer, route.reason or "natural_router")
        _inject_prior_context(event, context_key)
        hint = (
            "방금 자동 응답이 질문에 맞지 않았어. 질문 의도를 다시 정확히 파악해서 "
            "알맞은 도구로 답해줘."
        )
        existing = str(getattr(event, "channel_prompt", "") or "").strip()
        event.channel_prompt = (existing + "\n\n" + hint).strip() if existing else hint
        event.academy_self_check = True
        return {"action": "allow"}
    if _inject_prior_context(event, context_key):
        event.academy_self_check = True
    return {"action": "allow"}


def _route_response(text: str, reason: str) -> dict[str, object]:
    return {
        "action": "respond",
        "text": text,
        "route": "academy_ops",
        "reason": reason,
        "intent": f"academy.{reason}",
        "confidence": 0.8,
        "evidence": [reason],
        "priority": ACADEMY_ROUTE_PRIORITY,
    }


async def _guidance_text(user_text: str, intent: str, fallback: str) -> str:
    return await naturalize_guidance_response(user_text=user_text, intent=intent, fallback=fallback)


def _persist_handled_turn(session_store: Any, event: Any, question: str, answer: str) -> None:
    if session_store is None or not str(answer or "").strip():
        return
    source = getattr(event, "source", None)
    if source is None:
        return
    try:
        session_id = session_store.get_or_create_session(source).session_id
        ts = datetime.now().isoformat()
        session_store.append_to_transcript(session_id, {"role": "user", "content": question, "timestamp": ts})
        session_store.append_to_transcript(session_id, {"role": "assistant", "content": answer, "timestamp": ts})
    except Exception as exc:  # noqa: BLE001 - never fail the reply over a transcript write
        logger.debug("academy HANDLED transcript persist failed: %s", exc)


def _inject_prior_context(event: Any, context_key: str) -> bool:
    note = format_context_note(get_thread_context(context_key))
    if not note:
        return False
    existing = str(getattr(event, "channel_prompt", "") or "").strip()
    event.channel_prompt = (existing + "\n\n" + note).strip() if existing else note
    return True
