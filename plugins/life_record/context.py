"""Discord thread context for life record tools."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import Any

from gateway.discord_workspace import ensure_workspace
from miho_constants import get_miho_home


GUILD_ID: ContextVar[str] = ContextVar("life_record_guild_id", default="")
CHANNEL_ID: ContextVar[str] = ContextVar("life_record_channel_id", default="")
CHANNEL_NAME: ContextVar[str] = ContextVar("life_record_channel_name", default="")
THREAD_ID: ContextVar[str] = ContextVar("life_record_thread_id", default="")
THREAD_NAME: ContextVar[str] = ContextVar("life_record_thread_name", default="")


def capture_gateway_context(event: Any = None) -> None:
    source = getattr(event, "source", None)
    parent_chat_id = str(getattr(source, "parent_chat_id", "") or "")
    chat_id = str(getattr(source, "chat_id", "") or "")
    thread_id = str(getattr(source, "thread_id", "") or "")
    if parent_chat_id and not thread_id:
        thread_id = chat_id
    GUILD_ID.set(str(getattr(source, "guild_id", "") or ""))
    CHANNEL_ID.set(parent_chat_id or chat_id)
    CHANNEL_NAME.set(str(getattr(source, "parent_chat_name", "") or parent_chat_id or chat_id))
    THREAD_ID.set(thread_id)
    THREAD_NAME.set(str(getattr(source, "chat_name", "") or thread_id))


def current_life_record_dir() -> Path:
    channel_id = CHANNEL_ID.get().strip()
    if channel_id:
        workspace = ensure_workspace(
            guild_id=GUILD_ID.get(),
            channel_id=channel_id,
            channel_name=CHANNEL_NAME.get(),
            thread_id=THREAD_ID.get(),
            thread_name=THREAD_NAME.get(),
        )
        return workspace.active_dir / "life_records"
    return get_miho_home() / "life_records" / "local"
