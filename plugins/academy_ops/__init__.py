"""Academy operations plugin for PACA/Peak Discord workflows."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
import json
from typing import Any

from .auth_flow import LINK_TTL_SECONDS, create_login_link, resolve_auth_base_url
from .auth_store import delete_binding, get_binding
from .catalog import operations_payload
from .discord_button import send_discord_link_button
from .formatting import (
    format_binding_status,
    format_catalog,
    format_intent_preview,
    format_login_button_prompt,
    format_login_link,
)
from .intent import draft_intent
from .trigger import detect_academy_trigger

_DISCORD_USER_ID: ContextVar[str] = ContextVar("academy_ops_discord_user_id", default="")
_GUILD_ID: ContextVar[str] = ContextVar("academy_ops_guild_id", default="")
_CHANNEL_ID: ContextVar[str] = ContextVar("academy_ops_channel_id", default="")


def _catalog_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    """Return the academy operation catalog.

    Plugin tools may receive execution metadata such as ``task_id`` as keyword
    arguments from the tool dispatcher, so accept and ignore extra kwargs.
    """
    return json.dumps(operations_payload(), ensure_ascii=False)


def _academy_command(raw_args: str = "") -> str:
    text = raw_args.strip()
    if not text:
        return format_catalog()
    subcommand, _, remainder = text.partition(" ")
    normalized = subcommand.lower().strip()
    if normalized == "login":
        return _login_command()
    if normalized == "status":
        return _status_command()
    if normalized == "logout":
        return _logout_command()
    if normalized == "link":
        return _login_command()
    return format_intent_preview(draft_intent(text))


def _login_command() -> str:
    discord_user_id = _DISCORD_USER_ID.get()
    if not discord_user_id:
        return "디스코드 사용자 정보를 확인하지 못했어. 디스코드에서 `/academy login`으로 다시 실행해줘."
    link = create_login_link(
        discord_user_id=discord_user_id,
        guild_id=_GUILD_ID.get(),
        channel_id=_CHANNEL_ID.get(),
    )
    base_url = resolve_auth_base_url()
    return format_login_link(
        link.url,
        LINK_TTL_SECONDS // 60,
        is_local=base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost"),
    )


def _status_command() -> str:
    discord_user_id = _DISCORD_USER_ID.get()
    if not discord_user_id:
        return "디스코드 사용자 정보를 확인하지 못했어."
    binding = get_binding(discord_user_id)
    if binding is None:
        return "아직 학원 계정이 연결되지 않았어. `/academy login`으로 먼저 연결해줘."
    return format_binding_status(binding.name, binding.academy_name, binding.role)


def _logout_command() -> str:
    discord_user_id = _DISCORD_USER_ID.get()
    if not discord_user_id:
        return "디스코드 사용자 정보를 확인하지 못했어."
    if delete_binding(discord_user_id):
        return "학원 계정 연결을 해제했어."
    return "연결된 학원 계정이 없었어."


def _capture_gateway_context(event: Any = None, **kwargs: Any) -> dict[str, str]:
    source = getattr(event, "source", None)
    command = event.get_command() if event is not None and hasattr(event, "get_command") else ""
    if command != "academy":
        natural_result = _handle_natural_trigger(event, **kwargs)
        if natural_result is not None:
            return natural_result
        return {"action": "allow"}
    _DISCORD_USER_ID.set(str(getattr(source, "user_id", "") or ""))
    _GUILD_ID.set(str(getattr(source, "guild_id", "") or ""))
    _CHANNEL_ID.set(str(getattr(source, "chat_id", "") or ""))
    return {"action": "allow"}


def _handle_natural_trigger(event: Any = None, **kwargs: Any) -> dict[str, str] | None:
    text = str(getattr(event, "text", "") or "")
    trigger = detect_academy_trigger(text)
    if not trigger.should_prompt:
        return None

    source = getattr(event, "source", None)
    discord_user_id = str(getattr(source, "user_id", "") or "")
    if not discord_user_id:
        return None
    if not _is_authorized(event, kwargs.get("gateway")):
        return None

    _DISCORD_USER_ID.set(discord_user_id)
    _GUILD_ID.set(str(getattr(source, "guild_id", "") or ""))
    _CHANNEL_ID.set(str(getattr(source, "chat_id", "") or ""))

    binding = get_binding(discord_user_id)
    if binding is not None:
        return {"action": "rewrite", "text": "/academy"}

    if _schedule_login_button(event, kwargs.get("gateway")):
        return {"action": "skip", "reason": "academy_ops_login_button"}
    return {"action": "rewrite", "text": "/academy login"}


def _schedule_login_button(event: Any, gateway: Any = None) -> bool:
    source = getattr(event, "source", None)
    platform = str(getattr(getattr(source, "platform", None), "value", getattr(source, "platform", "")))
    if platform != "discord":
        return False
    adapters = getattr(gateway, "adapters", {}) if gateway is not None else {}
    adapter = adapters.get(getattr(source, "platform", None))
    if adapter is None:
        return False

    link = create_login_link(
        discord_user_id=str(getattr(source, "user_id", "") or ""),
        guild_id=str(getattr(source, "guild_id", "") or ""),
        channel_id=str(getattr(source, "chat_id", "") or ""),
    )
    base_url = resolve_auth_base_url()
    content = format_login_button_prompt(
        LINK_TTL_SECONDS // 60,
        is_local=base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost"),
    )
    metadata: dict[str, str] = {}
    thread_id = getattr(source, "thread_id", None)
    if thread_id:
        metadata["thread_id"] = str(thread_id)

    async def _send() -> None:
        await send_discord_link_button(
            adapter=adapter,
            chat_id=str(getattr(source, "chat_id", "") or ""),
            content=content,
            button_label="학원 계정 연결하기",
            url=link.url,
            title="PACA/Peak 학원관리 연결",
            metadata=metadata,
        )

    try:
        asyncio.get_running_loop().create_task(_send())
    except RuntimeError:
        return False
    return True


def _is_authorized(event: Any, gateway: Any = None) -> bool:
    checker = getattr(gateway, "_is_user_authorized", None)
    if checker is None:
        return True
    try:
        return bool(checker(getattr(event, "source", None)))
    except Exception:
        return False


def register(ctx: Any) -> None:
    ctx.register_command(
        "academy",
        _academy_command,
        description="PACA/Peak 로그인 연결, 기능 카탈로그, 실행 전 미리보기",
        args_hint="[요청]",
    )
    ctx.register_hook("pre_gateway_dispatch", _capture_gateway_context)
    ctx.register_tool(
        name="academy_operations_catalog",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_catalog_tool_handler,
        description="Return the PACA/Peak Discord operation catalog and safety policy.",
    )
