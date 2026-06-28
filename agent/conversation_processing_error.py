"""Outer response-processing error recovery for the conversation loop."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessingErrorResult:
    action: str
    messages: List[Dict[str, Any]]
    final_response: str | None = None
    turn_exit_reason: str = ""


def handle_response_processing_exception(
    *,
    agent: Any,
    error: Exception,
    messages: List[Dict[str, Any]],
    api_call_count: int,
) -> ProcessingErrorResult:
    """Handle exceptions raised after a successful API response."""

    error_msg = f"Error during OpenAI-compatible API call #{api_call_count}: {str(error)}"
    try:
        print(f"❌ {error_msg}")
    except (OSError, ValueError):
        logger.error(error_msg)

    logger.debug("Outer loop error in API call #%d", api_call_count, exc_info=True)
    _fill_missing_tool_results(messages, error_msg)

    if api_call_count >= agent.max_iterations - 1:
        final_response = f"I apologize, but I encountered repeated errors: {error_msg}"
        messages.append({"role": "assistant", "content": final_response})
        return ProcessingErrorResult(
            action="break",
            messages=messages,
            final_response=final_response,
            turn_exit_reason=f"error_near_max_iterations({error_msg[:80]})",
        )

    return ProcessingErrorResult(action="continue", messages=messages)


def _fill_missing_tool_results(messages: List[Dict[str, Any]], error_msg: str) -> None:
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        if not isinstance(msg, dict):
            break
        if msg.get("role") == "tool":
            continue
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            answered_ids = {
                m["tool_call_id"]
                for m in messages[idx + 1:]
                if isinstance(m, dict) and m.get("role") == "tool"
            }
            for tc in msg["tool_calls"]:
                if not tc or not isinstance(tc, dict):
                    continue
                if tc["id"] not in answered_ids:
                    messages.append({
                        "role": "tool",
                        "name": _get_tool_call_name_static(tc),
                        "tool_call_id": tc["id"],
                        "content": f"Error executing tool: {error_msg}",
                    })
        break


def _get_tool_call_name_static(tool_call: Dict[str, Any]) -> str:
    import run_agent

    return run_agent.AIAgent._get_tool_call_name_static(tool_call)
