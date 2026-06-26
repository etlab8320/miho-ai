"""Gateway turn context for Governance OS routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_dispatch_turn_context(event: Any) -> dict[str, Any]:
    source = getattr(event, "source", None)
    return {
        "platform": _source_value(getattr(source, "platform", "")),
        "guild_id": _compact(getattr(source, "guild_id", "")),
        "chat_id": _compact(getattr(source, "chat_id", "")),
        "thread_id": _compact(getattr(source, "thread_id", "")),
        "media": _media_summaries(getattr(event, "media_urls", None) or ()),
        "reply_to_text": _compact(getattr(event, "reply_to_text", "")),
        "channel_context": _compact(getattr(event, "channel_context", "")),
        "channel_prompt": _compact(getattr(event, "channel_prompt", ""), limit=600),
    }


def _media_summaries(values: Any) -> list[str]:
    summaries: list[str] = []
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        suffix = Path(raw).suffix.lower()
        summaries.append(suffix or raw[:40])
    return summaries


def _source_value(value: Any) -> str:
    return _compact(getattr(value, "value", value))


def _compact(value: Any, *, limit: int = 420) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."
