"""Short-lived thread context for follow-up academy requests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


STUDENT_CONTEXT_TOOLS = {
    "academy_student_attendance_calendar_image",
    "academy_student_attendance_range",
    "academy_student_summary",
    "academy_student_card_image",
    "academy_student_context",
}
CONTEXT_TTL = timedelta(minutes=30)
_CONTEXTS: dict[str, dict[str, Any]] = {}


def academy_context_key(event: Any) -> str:
    source = getattr(event, "source", None)
    platform = str(getattr(getattr(source, "platform", None), "value", "") or "")
    parts = [
        platform,
        str(getattr(source, "guild_id", "") or ""),
        str(getattr(source, "chat_id", "") or ""),
        str(getattr(source, "thread_id", "") or ""),
        str(getattr(source, "user_id", "") or ""),
    ]
    return ":".join(parts)


def get_thread_context(key: str | None) -> dict[str, Any]:
    if not key:
        return {}
    item = _CONTEXTS.get(key)
    if not item:
        return {}
    updated_at = item.get("updated_at")
    if not isinstance(updated_at, datetime) or datetime.now(timezone.utc) - updated_at > CONTEXT_TTL:
        _CONTEXTS.pop(key, None)
        return {}
    return {name: value for name, value in item.items() if name != "updated_at"}


def remember_thread_context(
    key: str | None,
    *,
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    if not key or tool_name not in STUDENT_CONTEXT_TOOLS or not payload.get("ok"):
        return
    student = payload.get("student") if isinstance(payload.get("student"), dict) else {}
    card = payload.get("card") if isinstance(payload.get("card"), dict) else {}
    profile = card.get("profile") if isinstance(card.get("profile"), dict) else {}
    student_query = str(args.get("student_query") or student.get("name") or profile.get("name") or "").strip()
    if not student_query:
        return
    _CONTEXTS[key] = {
        "kind": "student",
        "tool": tool_name,
        "student_query": student_query,
        "start_date": str(payload.get("start_date") or args.get("start_date") or ""),
        "end_date": str(payload.get("end_date") or args.get("end_date") or ""),
        "today": str(args.get("today") or ""),
        "period_days": args.get("period_days"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "updated_at": datetime.now(timezone.utc),
    }


def remember_pending_request(
    key: str | None,
    *,
    tool_name: str,
    args: dict[str, Any],
    request_text: str,
    reason: str,
) -> None:
    if not key:
        return
    _CONTEXTS[key] = {
        "kind": "pending_request",
        "tool": tool_name,
        "args": dict(args),
        "request_text": request_text,
        "reason": reason,
        "updated_at": datetime.now(timezone.utc),
    }


def pop_pending_request(key: str | None) -> dict[str, Any]:
    context = get_thread_context(key)
    if context.get("kind") != "pending_request":
        return {}
    _CONTEXTS.pop(str(key), None)
    return context


def clear_thread_contexts() -> None:
    _CONTEXTS.clear()
