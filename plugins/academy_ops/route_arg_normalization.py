"""Normalize LLM route arguments before academy tool execution."""

from __future__ import annotations

from typing import Any

from .route_overrides import forced_tool_for_output_request


STUDENT_RECORD_LOOKUP_TOOL = "academy_student_record_lookup"
DEFAULT_STUDENT_RECORD_PERIOD_DAYS = 30


def normalize_route_args(tool_name: str, args: dict[str, Any], *, today: str | None = None) -> dict[str, Any]:
    if tool_name == "academy_student_record_chart_image":
        return _student_record_chart_args(args)
    if tool_name != STUDENT_RECORD_LOOKUP_TOOL:
        return args
    resolved = dict(args)
    date_text = str(resolved.get("date") or "").strip()[:10]
    today_text = str(resolved.get("today") or today or "").strip()[:10]
    event_query = str(resolved.get("event_query") or "").strip()
    period_days = _int_or_none(resolved.get("period_days"))
    if date_text and today_text and date_text == today_text and not event_query and (period_days is None or period_days <= 1):
        resolved["period_days"] = DEFAULT_STUDENT_RECORD_PERIOD_DAYS
        resolved["fallback_recent_when_empty"] = True
    return resolved


def normalize_route_decision_tools(text: str, decision: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(decision)
    tool_name = str(resolved.get("tool") or "").strip()
    forced_tool = forced_tool_for_output_request(text, tool_name)
    if forced_tool:
        resolved["tool"] = forced_tool
        resolved["args"] = _normalized_forced_args(tool_name, forced_tool, resolved.get("args"))
    actions = resolved.get("actions")
    if isinstance(actions, list):
        resolved["actions"] = [_normalized_action_tool(text, action) for action in actions]
    return resolved


def _normalized_action_tool(text: str, action: Any) -> Any:
    if not isinstance(action, dict):
        return action
    resolved = dict(action)
    tool_name = str(resolved.get("tool") or "").strip()
    forced_tool = forced_tool_for_output_request(text, tool_name)
    if forced_tool:
        resolved["tool"] = forced_tool
        resolved["args"] = _normalized_forced_args(tool_name, forced_tool, resolved.get("args"))
    return resolved


def _normalized_forced_args(source_tool: str, target_tool: str, args: Any) -> dict[str, Any]:
    if source_tool == STUDENT_RECORD_LOOKUP_TOOL and target_tool == "academy_student_record_chart_image":
        return _student_record_chart_args(args if isinstance(args, dict) else {})
    return dict(args) if isinstance(args, dict) else {}


def _student_record_chart_args(args: dict[str, Any]) -> dict[str, Any]:
    period_days = _int_or_none(args.get("period_days"))
    limit = period_days if period_days is not None and 1 < period_days <= 10 else _int_or_none(args.get("limit")) or 5
    return {
        "student_query": str(args.get("student_query") or "").strip(),
        "event_query": str(args.get("event_query") or "").strip(),
        "today": str(args.get("today") or "").strip(),
        "period_days": period_days if period_days is not None and period_days > 10 else 180,
        "limit": max(2, min(limit, 10)),
    }


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
