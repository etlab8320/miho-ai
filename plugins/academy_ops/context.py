"""Gateway context for academy operations tools."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any


DISCORD_USER_ID: ContextVar[str] = ContextVar("academy_ops_discord_user_id", default="")
GUILD_ID: ContextVar[str] = ContextVar("academy_ops_guild_id", default="")
CHANNEL_ID: ContextVar[str] = ContextVar("academy_ops_channel_id", default="")


def capture_gateway_context(event: Any = None) -> None:
    source = getattr(event, "source", None)
    DISCORD_USER_ID.set(str(getattr(source, "user_id", "") or ""))
    GUILD_ID.set(str(getattr(source, "guild_id", "") or ""))
    CHANNEL_ID.set(str(getattr(source, "chat_id", "") or ""))


def current_discord_user_id() -> str:
    return DISCORD_USER_ID.get().strip()
