"""Compact current-turn tool evidence for final delivery agents."""

from __future__ import annotations

import re
from typing import Any


_MAX_ITEMS = 8
_MAX_CONTENT_CHARS = 1800
_SECRET_SHAPED_RE = re.compile(
    r"(?i)(?:token|api[_-]?key|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"
)


def current_turn_tool_evidence(messages: Any) -> list[dict[str, str]]:
    if not isinstance(messages, list):
        return []
    current_turn = _current_turn_messages(messages)
    evidence: list[dict[str, str]] = []
    for message in current_turn:
        if not isinstance(message, dict) or message.get("role") not in {"tool", "function"}:
            continue
        tool_name = str(message.get("name") or message.get("tool_name") or "").strip()
        if not tool_name:
            continue
        content = _compact_text(message.get("content"))
        if not content:
            continue
        evidence.append({"tool_name": tool_name, "content": content})
    return evidence[-_MAX_ITEMS:]


def _current_turn_messages(messages: list[Any]) -> list[dict[str, Any]]:
    typed = [message for message in messages if isinstance(message, dict)]
    last_user_index = -1
    for index, message in enumerate(typed):
        if message.get("role") == "user":
            last_user_index = index
    return typed[last_user_index + 1 :] if last_user_index >= 0 else typed


def _compact_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = _SECRET_SHAPED_RE.sub(lambda _match: "<redacted-secret>", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    if len(text) <= _MAX_CONTENT_CHARS:
        return text
    head = text[: _MAX_CONTENT_CHARS // 2].rstrip()
    tail = text[-(_MAX_CONTENT_CHARS // 2) :].lstrip()
    return f"{head}\n...[truncated]...\n{tail}"
