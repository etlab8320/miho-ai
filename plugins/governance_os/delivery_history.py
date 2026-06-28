"""Current-turn tool outcome extraction for final delivery."""

from __future__ import annotations

import json
from typing import Any

from .delivery_gate_constants import PLAYBOOK_BY_TOOL
from .registry import GovernanceRegistry
from .review import auxiliary_review_policy_for_playbook, evaluate_review_gate


def outcomes_from_conversation_history(
    registry: GovernanceRegistry,
    messages: Any,
    *,
    user_text: str,
) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    current_turn = messages[_current_turn_start(messages, user_text) :]
    outcomes: list[dict[str, Any]] = []
    for message in current_turn:
        if not isinstance(message, dict) or str(message.get("role") or "") != "tool":
            continue
        tool_name = str(message.get("name") or message.get("tool_name") or "").strip()
        playbook_key = PLAYBOOK_BY_TOOL.get(tool_name)
        if not playbook_key:
            continue
        payload = _loads_object(message.get("content"))
        if payload is None:
            continue
        review = evaluate_review_gate(
            registry,
            playbook_key=playbook_key,
            tool_name=tool_name,
            result=payload,
            auxiliary_review_policy=auxiliary_review_policy_for_playbook(playbook_key),
        )
        outcomes.append(
            {
                "playbook_key": playbook_key,
                "review_status": review.status,
                "tools_used": _tools_used(tool_name, payload),
                "failures": _review_failures(review),
            }
        )
    return outcomes


def _current_turn_start(messages: list[Any], user_text: str) -> int:
    fallback = 0
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or str(message.get("role") or "") != "user":
            continue
        fallback = index + 1
        content = _message_text(message.get("content"))
        if user_text and user_text in content:
            return index + 1
    return fallback


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(part for part in parts if part)
    return str(value or "")


def _loads_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    text = _message_text(value)
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _review_failures(review: Any) -> list[str]:
    if getattr(review, "status", "") == "pass":
        return []
    reason = str(getattr(review, "reason", "") or "").strip()
    return [reason] if reason else ["review_not_passed"]


def _tools_used(tool_name: str, payload: dict[str, Any]) -> list[str]:
    tools = [tool_name]
    for item in payload.get("governance_tools_used") or []:
        text = str(item or "").strip()
        if text and text not in tools:
            tools.append(text)
    return tools
