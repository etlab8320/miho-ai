"""Nous Portal preflight guard for API retry loops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class NousPreflightResult:
    action: str
    return_value: Dict[str, Any] | None = None


def handle_nous_rate_limit_preflight(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
) -> NousPreflightResult:
    """Skip a Nous API call when another session already saw a real 429."""

    if agent.provider != "nous":
        return NousPreflightResult("proceed")
    try:
        from agent.nous_rate_guard import (
            format_remaining as format_nous_remaining,
            nous_rate_limit_remaining,
        )

        nous_remaining = nous_rate_limit_remaining()
        if nous_remaining is None or nous_remaining <= 0:
            return NousPreflightResult("proceed")

        nous_msg = (
            "Nous Portal rate limit active — "
            f"resets in {format_nous_remaining(nous_remaining)}."
        )
        agent._vprint(
            f"{agent.log_prefix}⏳ {nous_msg} Trying fallback...",
            force=True,
        )
        agent._emit_status(f"⏳ {nous_msg}")
        if agent._try_activate_fallback():
            return NousPreflightResult("continue")

        agent._persist_session(messages, conversation_history)
        return NousPreflightResult(
            "return",
            {
                "final_response": (
                    f"⏳ {nous_msg}\n\n"
                    "No fallback provider available. Try again after the reset, "
                    "or add a fallback provider in config.yaml."
                ),
                "messages": messages,
                "api_calls": api_call_count,
                "completed": False,
                "failed": True,
                "error": nous_msg,
            },
        )
    except ImportError:
        return NousPreflightResult("proceed")
    except Exception:
        return NousPreflightResult("proceed")
