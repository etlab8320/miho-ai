"""Conversation safety guard for low-information gateway turns."""

from __future__ import annotations

import re
from typing import Any


_MAX_LOW_INFORMATION_CHARS = 8
_HANGUL_SYLLABLE_RE = re.compile(r"[가-힣]")
_WORD_OR_DIGIT_RE = re.compile(r"[A-Za-z0-9가-힣]")
_JAMO_OR_NOISE_RE = re.compile(r"^[ㄱ-ㅎㅏ-ㅣㅋㅎㅠㅜ\W_]+$")
_ACKNOWLEDGEMENTS = {
    "응",
    "네",
    "예",
    "아니",
    "아니요",
    "ㅇㅋ",
    "오케이",
    "ㄱ",
    "ㄱㄱ",
    "고",
    "승인",
}
_COMMAND_PREFIXES = ("/", "!", ".")
_CLARIFY_TEXT = "방금 메시지는 의미를 정확히 잡기 어려워요. 원하는 작업을 한 문장으로 다시 말해 주세요."
_ROUTE_PRIORITY = -100


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def is_low_information_message(text: str) -> bool:
    """Return True when a turn is too ambiguous to answer from memory."""
    normalized = _normalized_text(text)
    if not normalized:
        return False
    if normalized in _ACKNOWLEDGEMENTS:
        return False
    if normalized.startswith(_COMMAND_PREFIXES):
        return False
    if len(normalized) > _MAX_LOW_INFORMATION_CHARS:
        return False
    if _HANGUL_SYLLABLE_RE.search(normalized):
        return False
    if not _WORD_OR_DIGIT_RE.search(normalized):
        return True
    return bool(_JAMO_OR_NOISE_RE.fullmatch(normalized))


async def _guard_pre_gateway_dispatch(event: Any = None, **_: Any) -> dict[str, object]:
    text = _normalized_text(getattr(event, "text", ""))
    if is_low_information_message(text):
        return {
            "action": "respond",
            "text": _CLARIFY_TEXT,
            "route": "conversation_guard",
            "reason": "low_information",
            "priority": _ROUTE_PRIORITY,
        }
    return {"action": "allow"}


def register(ctx: Any) -> None:
    ctx.register_hook("pre_gateway_dispatch", _guard_pre_gateway_dispatch)


__all__ = [
    "_guard_pre_gateway_dispatch",
    "is_low_information_message",
]
