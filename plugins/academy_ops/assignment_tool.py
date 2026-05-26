"""Tool handler for read-only Peak class assignment lookup."""

from __future__ import annotations

from datetime import date
import json
from typing import Any

from .academy_api import AcademyApiError
from .academy_query_tools import _resolve_client
from .assignment_lookup import assignments_for_day
from .response_guidance import academy_response_guidance

_MESSAGE_LIMIT = 12


def _assignment_by_date_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    target_day = _date_arg(payload.get("date"))
    if target_day is None:
        return _json_error("조회 날짜를 YYYY-MM-DD로 지정해줘.")
    time_slot = str(payload.get("time_slot") or "").strip()
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        assignments = assignments_for_day(client_or_error, target_day, time_slot=time_slot)
    except AcademyApiError as exc:
        return _json_error(str(exc))
    return _json_ok(
        {
            "operation": "assignment.by_date",
            **assignments,
            "message": _assignment_message(assignments),
            "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
        }
    )


def _assignment_message(payload: dict[str, Any]) -> str:
    date_text = str(payload.get("date") or "")
    slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
    if not slots:
        return f"{date_text} 반배치는 없어."
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines = [
        (
            f"{date_text} 반배치: {summary.get('classes', 0)}개 반, "
            f"배정 {summary.get('assigned_students', 0)}명, 미배정 {summary.get('waiting_students', 0)}명"
        )
    ]
    for slot, body in slots.items():
        if not isinstance(body, dict):
            continue
        lines.append(f"{_slot_label(str(slot))}")
        for class_row in _dict_rows(body.get("classes")):
            instructor_names = _names(class_row.get("instructors"))
            student_names = _names(class_row.get("students"), key="student_name")
            class_name = f"{class_row.get('class_num')}반" if class_row.get("class_num") else "반 미지정"
            teacher = f" / {', '.join(instructor_names)}" if instructor_names else ""
            lines.append(f"- {class_name}{teacher}: {', '.join(student_names[:_MESSAGE_LIMIT])}")
            if len(student_names) > _MESSAGE_LIMIT:
                lines.append(f"  외 {len(student_names) - _MESSAGE_LIMIT}명")
        waiting_names = _names(body.get("waiting_students"), key="student_name")
        if waiting_names:
            lines.append(f"- 미배정: {', '.join(waiting_names[:_MESSAGE_LIMIT])}")
            if len(waiting_names) > _MESSAGE_LIMIT:
                lines.append(f"  외 {len(waiting_names) - _MESSAGE_LIMIT}명")
    return "\n".join(lines)


def _date_arg(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _names(rows: Any, *, key: str = "name") -> list[str]:
    return [str(row.get(key) or "") for row in _dict_rows(rows) if row.get(key)]


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)] if isinstance(value, list) else []


def _slot_label(value: str) -> str:
    return {"morning": "오전반", "afternoon": "오후반", "evening": "저녁반"}.get(value, value or "시간대 미지정")


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


def _json_ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)
