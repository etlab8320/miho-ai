"""Transport error classification for agentic governance calls."""

from __future__ import annotations


def transport_status(exc: Exception) -> str:
    """Return a coarse transport status, without semantic domain judgement."""

    text = str(exc).casefold()
    if "timeout" in text or "timed out" in text or "exceeded" in text:
        return "timeout"
    if "unavailable" in text:
        return "unavailable"
    return "error"


def is_timeout_error(exc: Exception) -> bool:
    return transport_status(exc) == "timeout"
