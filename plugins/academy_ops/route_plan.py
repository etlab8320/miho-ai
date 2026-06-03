"""Execute LLM-proposed multi-tool academy route plans."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from .natural_router_payload import load_payload, payload_message, tool_timeout_message
from .route_arg_normalization import normalize_route_args
from .routing_decision import reject_execute_reason
from .thread_context import remember_thread_context

ToolHandler = Callable[..., str]
ArgsResolver = Callable[[str, dict[str, Any], str | None], dict[str, Any]]
TodayResolver = Callable[[str, dict[str, Any], str | None], dict[str, Any]]


async def execute_route_plan(
    decision: dict[str, Any],
    *,
    handlers: dict[str, ToolHandler],
    min_confidence: float,
    tool_timeout: float,
    today: str | None,
    context_key: str | None,
    resolve_args: ArgsResolver,
    with_reference_today: TodayResolver,
) -> str | None:
    actions = decision.get("actions")
    if not isinstance(actions, list) or not actions:
        return None
    messages: list[str] = []
    for index, action in enumerate(actions, start=1):
        if not isinstance(action, dict):
            return None
        tool_name = str(action.get("tool") or "").strip()
        step = _step_decision(decision, action, tool_name)
        if reject_execute_reason(step, allowed_tools=handlers.keys(), min_confidence=min_confidence):
            return None
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        args = with_reference_today(tool_name, resolve_args(tool_name, args, context_key), today)
        args = normalize_route_args(tool_name, args, today=today)
        payload = await _run_tool(handlers[tool_name], args, tool_timeout=tool_timeout)
        remember_thread_context(context_key, tool_name=tool_name, args=args, payload=payload)
        messages.append(_format_step(index, action, payload))
    return "\n\n".join(messages)


def _step_decision(parent: dict[str, Any], action: dict[str, Any], tool_name: str) -> dict[str, Any]:
    return {
        "action": "execute",
        "domain": parent.get("domain"),
        "intent": action.get("intent") or parent.get("intent"),
        "evidence": action.get("evidence") or parent.get("evidence"),
        "ambiguous": parent.get("ambiguous", False),
        "tool": tool_name,
        "confidence": action.get("confidence", parent.get("confidence")),
    }


async def _run_tool(handler: ToolHandler, args: dict[str, Any], *, tool_timeout: float) -> dict[str, Any]:
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(handler, args), timeout=tool_timeout)
    except TimeoutError:
        return {"ok": False, "message": tool_timeout_message()}
    except Exception:
        return {"ok": False, "message": "학원 데이터를 조회하다가 오류가 났어."}
    return load_payload(raw)


def _format_step(index: int, action: dict[str, Any], payload: dict[str, Any]) -> str:
    title = str(action.get("title") or action.get("intent") or f"조회 {index}").strip()
    return f"{title}\n{payload_message(payload)}"
