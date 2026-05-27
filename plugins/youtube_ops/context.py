"""Gateway context capture for YouTube tools."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any


EVENT_CONTEXT: ContextVar[Any | None] = ContextVar("youtube_ops_event_context", default=None)
GUILD_ID: ContextVar[str] = ContextVar("youtube_ops_guild_id", default="")
CHANNEL_ID: ContextVar[str] = ContextVar("youtube_ops_channel_id", default="")
CHANNEL_NAME: ContextVar[str] = ContextVar("youtube_ops_channel_name", default="")
THREAD_ID: ContextVar[str] = ContextVar("youtube_ops_thread_id", default="")
THREAD_NAME: ContextVar[str] = ContextVar("youtube_ops_thread_name", default="")
USER_ID: ContextVar[str] = ContextVar("youtube_ops_user_id", default="")


def capture_gateway_context(event: Any = None) -> None:
    source = getattr(event, "source", None)
    parent_chat_id = str(getattr(source, "parent_chat_id", "") or "")
    chat_id = str(getattr(source, "chat_id", "") or "")
    thread_id = str(getattr(source, "thread_id", "") or "")
    if parent_chat_id and not thread_id:
        thread_id = chat_id
    EVENT_CONTEXT.set(event)
    GUILD_ID.set(str(getattr(source, "guild_id", "") or ""))
    CHANNEL_ID.set(parent_chat_id or chat_id)
    CHANNEL_NAME.set(str(getattr(source, "parent_chat_name", "") or getattr(source, "chat_name", "") or chat_id))
    THREAD_ID.set(thread_id)
    THREAD_NAME.set(str(getattr(source, "chat_name", "") or thread_id))
    USER_ID.set(str(getattr(source, "user_id", "") or ""))
