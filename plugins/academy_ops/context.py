"""Gateway context for academy operations tools."""

from __future__ import annotations

from contextvars import ContextVar
import re
from typing import Any


DISCORD_USER_ID: ContextVar[str] = ContextVar("academy_ops_discord_user_id", default="")
GUILD_ID: ContextVar[str] = ContextVar("academy_ops_guild_id", default="")
CHANNEL_ID: ContextVar[str] = ContextVar("academy_ops_channel_id", default="")
REQUEST_TEXT: ContextVar[str] = ContextVar("academy_ops_request_text", default="")


def capture_gateway_context(event: Any = None) -> None:
    source = getattr(event, "source", None)
    DISCORD_USER_ID.set(str(getattr(source, "user_id", "") or ""))
    GUILD_ID.set(str(getattr(source, "guild_id", "") or ""))
    CHANNEL_ID.set(str(getattr(source, "chat_id", "") or ""))
    REQUEST_TEXT.set(str(getattr(event, "text", "") or ""))


def current_discord_user_id() -> str:
    return DISCORD_USER_ID.get().strip()


def infer_student_query_from_current_request() -> str:
    text = REQUEST_TEXT.get().strip()
    for pattern in [
        r"([가-힣]{2,5})\s*(?:학생\s*)?카드",
        r"([가-힣]{2,5})\s*학생",
        r"([가-힣]{2,5})\s*(?:요약|상담|출결)",
    ]:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""
