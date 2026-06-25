"""Policy evaluation for Governance OS playbook tool contracts."""

from __future__ import annotations

import json
from typing import Any

from .models import PolicyDecision
from .registry import GovernanceRegistry


def evaluate_tool_call(
    registry: GovernanceRegistry,
    *,
    playbook_key: str,
    tool_name: str,
    args: dict[str, Any] | None = None,
) -> PolicyDecision:
    playbook = registry.get_playbook(playbook_key)
    forbidden_match = _matched_forbidden_contract(
        tool_name=tool_name,
        args=args,
        forbidden_tools=playbook.forbidden_tools,
    )
    if forbidden_match:
        return PolicyDecision(
            action="block",
            reason="forbidden_tool",
            playbook_key=playbook.key,
            tool_name=tool_name,
            message_ko=_forbidden_tool_message(playbook.required_tools),
            evidence=(forbidden_match, f"{tool_name} is forbidden by {playbook.key}"),
        )
    if tool_name in playbook.required_tools and playbook.review_gates:
        return PolicyDecision(
            action="review_required",
            reason="review_gate_required",
            playbook_key=playbook.key,
            tool_name=tool_name,
            message_ko="이 결과는 사용자에게 전달하기 전에 후검증을 통과해야 합니다.",
            evidence=(f"{tool_name} requires review gates",),
            review_gates=playbook.review_gates,
        )
    return PolicyDecision(
        action="allow",
        reason="tool_allowed",
        playbook_key=playbook.key,
        tool_name=tool_name,
        message_ko="",
    )


def _forbidden_tool_message(required_tools: tuple[str, ...]) -> str:
    return (
        "이 작업은 직접 코드나 일반 파일 생성으로 처리하면 안 됩니다. "
        "등록된 전용 도구를 사용하고, 결과는 후검증을 통과한 뒤 전달해야 합니다."
    )


def _matched_forbidden_contract(
    *,
    tool_name: str,
    args: dict[str, Any] | None,
    forbidden_tools: tuple[str, ...],
) -> str:
    if tool_name in forbidden_tools:
        return f"matched_forbidden_tool={tool_name}"
    blob = _args_blob(args)
    if not blob:
        return ""
    for forbidden in forbidden_tools:
        needle = " ".join(str(forbidden).casefold().split())
        if len(needle) >= 4 and needle in blob:
            return f"matched_forbidden_arg={forbidden}"
    return ""


def _args_blob(args: dict[str, Any] | None) -> str:
    if not args:
        return ""
    try:
        raw = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        raw = str(args)
    return " ".join(raw.casefold().split())
