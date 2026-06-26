"""Retry blocked final delivery with verified tool results."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .delivery_safety import contains_internal_guard_leak, contains_non_result_deferral
from .final_delivery_orchestrator import (
    FinalDeliveryToolStep,
    compose_final_delivery_answer,
    plan_final_delivery_retry,
)
from .registry import GovernanceRegistry
from .review import auxiliary_review_policy_for_playbook, evaluate_review_gate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FinalDeliveryRetryResult:
    answer: str
    tool_name: str
    tool_result: dict[str, Any]
    review_reason: str
    answer_source: str = "verified_tool_payload"


def retry_blocked_final_delivery(
    *,
    registry: GovernanceRegistry,
    playbook_key: str,
    retry_tools: tuple[str, ...],
    question: str,
    answer: str = "",
    conversation_history: Any,
    task_id: str = "",
    dispatch_tool: Callable[..., str] | None = None,
    orchestrator_call_llm: Callable[..., Any] | None = None,
    orchestrator_extract_content: Callable[[Any], str] | None = None,
) -> FinalDeliveryRetryResult | None:
    """Run a retry tool when current-turn args are available and review passes."""

    if not playbook_key or not retry_tools:
        return None
    retry_steps = _latest_retry_steps(conversation_history, retry_tools=retry_tools)
    used_orchestrator_plan = False
    if not retry_steps:
        retry_steps = plan_final_delivery_retry(
            question=question,
            answer=answer,
            playbook_key=playbook_key,
            retry_tools=retry_tools,
            conversation_history=conversation_history,
            evidence={"retry_tools": list(retry_tools), "playbook_key": playbook_key},
            call_llm=orchestrator_call_llm,
            extract_content=orchestrator_extract_content,
        )
        used_orchestrator_plan = bool(retry_steps)
    if not retry_steps:
        return None

    last_tool = ""
    last_payload: dict[str, Any] | None = None
    last_review_reason = ""
    verified_results: list[dict[str, Any]] = []
    for step in retry_steps:
        try:
            raw_result = _dispatch_tool(
                step.tool_name,
                step.args,
                task_id=task_id,
                dispatch_tool=dispatch_tool,
            )
        except Exception as exc:
            logger.info("final delivery retry dispatch failed: %s", exc)
            return None
        payload = _loads_object(raw_result)
        if payload is None:
            return None
        review = evaluate_review_gate(
            registry,
            playbook_key=playbook_key,
            tool_name=step.tool_name,
            result=payload,
            auxiliary_review_policy=auxiliary_review_policy_for_playbook(playbook_key),
        )
        if review.status != "pass":
            return None
        last_tool = step.tool_name
        last_payload = payload
        last_review_reason = review.reason
        verified_results.append(
            {
                "tool_name": step.tool_name,
                "args": step.args,
                "result": payload,
                "review_reason": review.reason,
            }
        )
    if last_payload is None:
        return None
    final_answer = ""
    answer_source = "verified_tool_payload"
    requires_orchestrator_answer = used_orchestrator_plan or orchestrator_call_llm is not None
    if requires_orchestrator_answer:
        final_answer = compose_final_delivery_answer(
            question=question,
            answer=answer,
            playbook_key=playbook_key,
            retry_tools=retry_tools,
            conversation_history=conversation_history,
            evidence={
                "retry_tools": list(retry_tools),
                "playbook_key": playbook_key,
                "verified_tool_results_count": len(verified_results),
            },
            verified_tool_results=tuple(verified_results),
            call_llm=orchestrator_call_llm,
            extract_content=orchestrator_extract_content,
        ) or ""
        if _usable_answer(final_answer):
            answer_source = "orchestrator_agent"
        else:
            return None
    if answer_source != "orchestrator_agent":
        final_answer = _answer_from_payload(question=question, payload=last_payload)
    if not _usable_answer(final_answer):
        return None
    return FinalDeliveryRetryResult(
        answer=final_answer,
        tool_name=last_tool,
        tool_result=last_payload,
        review_reason=last_review_reason,
        answer_source=answer_source,
    )


def _dispatch_tool(
    tool_name: str,
    args: dict[str, Any],
    *,
    task_id: str,
    dispatch_tool: Callable[..., str] | None,
) -> str:
    if dispatch_tool is not None:
        return dispatch_tool(tool_name, args, task_id=task_id or None)
    from tools.registry import registry as tool_registry

    return tool_registry.dispatch(tool_name, args, task_id=task_id or None)


def _latest_retry_steps(
    conversation_history: Any,
    *,
    retry_tools: tuple[str, ...],
) -> tuple[FinalDeliveryToolStep, ...]:
    tool_set = {str(tool).strip() for tool in retry_tools if str(tool).strip()}
    if not tool_set or not isinstance(conversation_history, list):
        return ()
    current_turn = _current_turn_messages(conversation_history)
    candidates: list[tuple[str, dict[str, Any]]] = []
    candidates.extend(_retry_args_from_tool_payloads(current_turn, tool_set))
    candidates.extend(_retry_args_from_assistant_calls(current_turn, tool_set))
    if not candidates:
        return ()
    tool_name, args = candidates[-1]
    return (FinalDeliveryToolStep(tool_name=tool_name, args=args),)


def _current_turn_messages(messages: list[Any]) -> list[dict[str, Any]]:
    typed = [msg for msg in messages if isinstance(msg, dict)]
    last_user_index = -1
    for index, msg in enumerate(typed):
        if msg.get("role") == "user":
            last_user_index = index
    return typed[last_user_index + 1 :] if last_user_index >= 0 else typed


def _retry_args_from_tool_payloads(
    messages: list[dict[str, Any]],
    tool_set: set[str],
) -> list[tuple[str, dict[str, Any]]]:
    candidates: list[tuple[str, dict[str, Any]]] = []
    for msg in messages:
        if msg.get("role") not in {"tool", "function"}:
            continue
        tool_name = str(msg.get("name") or msg.get("tool_name") or "").strip()
        payload = _loads_object(msg.get("content"))
        if payload is None:
            continue
        retry_args = _payload_retry_args(payload)
        if tool_name in tool_set:
            candidates.extend((tool_name, args) for args in retry_args)
        for retry_tool in _payload_retry_tools(payload, tool_set):
            candidates.extend((retry_tool, args) for args in retry_args)
    return candidates


def _payload_retry_args(payload: dict[str, Any]) -> list[dict[str, Any]]:
    args: list[dict[str, Any]] = []
    for container in (
        payload.get("auto_retry_executor"),
        payload.get("governance_review"),
        payload.get("reviewer"),
    ):
        if not isinstance(container, dict):
            continue
        for item in container.get("retry_args") or []:
            if isinstance(item, dict):
                args.append(item)
    return args


def _payload_retry_tools(payload: dict[str, Any], tool_set: set[str]) -> list[str]:
    tools: list[str] = []
    for container in (payload.get("auto_retry_executor"), payload.get("governance_review")):
        if not isinstance(container, dict):
            continue
        for item in container.get("retry_tools") or []:
            tool_name = str(item).strip()
            if tool_name in tool_set and tool_name not in tools:
                tools.append(tool_name)
    return tools


def _retry_args_from_assistant_calls(
    messages: list[dict[str, Any]],
    tool_set: set[str],
) -> list[tuple[str, dict[str, Any]]]:
    candidates: list[tuple[str, dict[str, Any]]] = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for call in msg.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            if not isinstance(function, dict):
                continue
            tool_name = str(function.get("name") or "").strip()
            if tool_name not in tool_set:
                continue
            args = _loads_object(function.get("arguments"))
            if args is not None:
                candidates.append((tool_name, args))
    return candidates


def _answer_from_payload(*, question: str, payload: dict[str, Any]) -> str:
    for key in ("delivery_text", "message", "answer", "summary"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    media_tag = str(payload.get("media_tag") or "").strip()
    if media_tag:
        return media_tag
    return ""


def _usable_answer(answer: str) -> bool:
    text = str(answer or "").strip()
    return bool(
        text
        and not contains_internal_guard_leak(text)
        and not contains_non_result_deferral(text)
    )


def _loads_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None
