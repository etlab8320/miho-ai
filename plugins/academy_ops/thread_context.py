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
STAFF_CONTEXT_TOOLS = {
    "academy_staff_attendance_range",
}
MONTHLY_TEST_CONTEXT_TOOLS = {
    "academy_monthly_test_records",
}
# Entity args a follow-up question naturally inherits when left unspecified
# ("그 학생", "여자 평균은?"): the subject carries over from the last turn. The
# key name encodes meaning, so inheritance only fires between tools that share
# the arg — student_query never leaks into a staff query, etc. Relative dates
# are intentionally excluded (carrying "오늘" into "내일은?" would be wrong);
# only student-range periods carry over, preserving prior behaviour.
INHERITABLE_ENTITY_ARGS = (
    "student_query",
    "staff_query",
    "event_query",
    "trainer_query",
)
CONTEXT_TTL = timedelta(minutes=30)
_CONTEXTS: dict[str, dict[str, Any]] = {}


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return not str(value).strip()


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
    if not key or not payload.get("ok"):
        return
    if tool_name in MONTHLY_TEST_CONTEXT_TOOLS:
        _remember_monthly_test_context(key, tool_name=tool_name, args=args, payload=payload)
        return
    if tool_name in STAFF_CONTEXT_TOOLS:
        _remember_staff_context(key, tool_name=tool_name, args=args, payload=payload)
        return
    if tool_name in STUDENT_CONTEXT_TOOLS:
        _remember_student_context(key, tool_name=tool_name, args=args, payload=payload)
        return
    _remember_generic_context(key, tool_name=tool_name, args=args)


def _remember_student_context(
    key: str,
    *,
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
) -> None:
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


def _remember_generic_context(key: str, *, tool_name: str, args: dict[str, Any]) -> None:
    """Remember entity args from any other successful tool so follow-ups can
    inherit them (e.g. record-lookup → '여자 평균은?'). Tools that carry no
    inheritable entity (e.g. a whole-day attendance lookup) leave the existing
    context untouched, so an unrelated turn never wipes the active subject.
    """
    entities = {
        name: str(args.get(name)).strip()
        for name in INHERITABLE_ENTITY_ARGS
        if not _is_blank(args.get(name))
    }
    if not entities:
        return
    record: dict[str, Any] = {
        "kind": "generic",
        "tool": tool_name,
        "updated_at": datetime.now(timezone.utc),
    }
    record.update(entities)
    for date_key in ("start_date", "end_date"):
        if not _is_blank(args.get(date_key)):
            record[date_key] = str(args[date_key]).strip()
    _CONTEXTS[key] = record


def _remember_monthly_test_context(
    key: str,
    *,
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    event_query = str(args.get("event_query") or "").strip()
    if not event_query:
        return
    test = payload.get("test") if isinstance(payload.get("test"), dict) else {}
    _CONTEXTS[key] = {
        "kind": "monthly_test",
        "tool": tool_name,
        "event_query": event_query,
        "test_id": test.get("id"),
        "test_month": str(test.get("test_month") or args.get("test_month") or ""),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "updated_at": datetime.now(timezone.utc),
    }


def _remember_staff_context(
    key: str,
    *,
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    staff_query = str(args.get("staff_query") or payload.get("staff_query") or "").strip()
    instructors = payload.get("instructors") if isinstance(payload.get("instructors"), list) else []
    if not staff_query and len(instructors) == 1 and isinstance(instructors[0], dict):
        staff_query = str(instructors[0].get("name") or "").strip()
    if not staff_query:
        return
    _CONTEXTS[key] = {
        "kind": "staff",
        "tool": tool_name,
        "staff_query": staff_query,
        "start_date": str(payload.get("start_date") or args.get("start_date") or ""),
        "end_date": str(payload.get("end_date") or args.get("end_date") or ""),
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
