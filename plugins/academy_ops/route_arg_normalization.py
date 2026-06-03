"""Normalize LLM route arguments before academy tool execution."""

from __future__ import annotations

from typing import Any


STUDENT_RECORD_LOOKUP_TOOL = "academy_student_record_lookup"
DEFAULT_STUDENT_RECORD_PERIOD_DAYS = 30


def normalize_route_args(tool_name: str, args: dict[str, Any], *, today: str | None = None) -> dict[str, Any]:
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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
