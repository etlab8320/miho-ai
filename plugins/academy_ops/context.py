"""Gateway context for academy operations tools."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any


DISCORD_USER_ID: ContextVar[str] = ContextVar("academy_ops_discord_user_id", default="")
GUILD_ID: ContextVar[str] = ContextVar("academy_ops_guild_id", default="")
CHANNEL_ID: ContextVar[str] = ContextVar("academy_ops_channel_id", default="")
REQUEST_TEXT: ContextVar[str] = ContextVar("academy_ops_request_text", default="")
GATEWAY_CONTEXT: ContextVar[Any | None] = ContextVar("academy_ops_gateway_context", default=None)
EVENT_CONTEXT: ContextVar[Any | None] = ContextVar("academy_ops_event_context", default=None)


def capture_gateway_context(event: Any = None) -> None:
    source = getattr(event, "source", None)
    DISCORD_USER_ID.set(str(getattr(source, "user_id", "") or ""))
    GUILD_ID.set(str(getattr(source, "guild_id", "") or ""))
    CHANNEL_ID.set(str(getattr(source, "chat_id", "") or ""))
    REQUEST_TEXT.set(str(getattr(event, "text", "") or ""))
    EVENT_CONTEXT.set(event)


def set_gateway_context(gateway: Any = None) -> None:
    GATEWAY_CONTEXT.set(gateway)


def current_gateway_context() -> Any | None:
    return GATEWAY_CONTEXT.get()


def current_event_context() -> Any | None:
    return EVENT_CONTEXT.get()


def current_discord_user_id() -> str:
    return DISCORD_USER_ID.get().strip()
