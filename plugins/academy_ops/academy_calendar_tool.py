"""Tool handlers for PACA academy schedules and consultations."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from .academy_api import AcademyApiError
from .academy_calendar import academy_schedules_for_range, consultation_schedules_for_range
from .academy_query_tools import _resolve_client
from .response_guidance import academy_response_guidance

_MESSAGE_LIMIT = 24


def _academy_schedule_range_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    date_range = _date_range(payload)
    if isinstance(date_range, str):
        return _json_error(date_range)
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        schedules = academy_schedules_for_range(client_or_error, date_range[0], date_range[1])
    except AcademyApiError as exc:
        return _json_error(str(exc))
    return _json_ok(
        {
            "operation": "academy.schedule_range",
            **schedules,
            "message": _academy_schedule_message(schedules),
            "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
        }
    )


def _consultation_schedule_range_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    date_range = _date_range(payload)
    if isinstance(date_range, str):
        return _json_error(date_range)
    new_only = _new_registration_only(payload.get("new_registration_only"))
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        consultations = consultation_schedules_for_range(
            client_or_error,
            date_range[0],
            date_range[1],
            new_registration_only=new_only,
        )
    except AcademyApiError as exc:
        return _json_error(str(exc))
    return _json_ok(
        {
            "operation": "consultation.schedule_range",
            **consultations,
            "message": _consultation_schedule_message(consultations),
            "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
        }
    )


def _date_range(payload: dict[str, Any]) -> tuple[date, date] | str:
    start = _date_arg(payload.get("start_date"))
    end = _date_arg(payload.get("end_date"))
    if start is None or end is None:
        return "조회 시작일과 종료일을 YYYY-MM-DD로 지정해줘."
    if end < start:
        return "조회 종료일이 시작일보다 빠를 수는 없어."
    return start, end


def _date_arg(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _academy_schedule_message(payload: dict[str, Any]) -> str:
    rows = [row for row in payload.get("schedules", []) if isinstance(row, dict)]
    label = _range_label(payload)
    if not rows:
        return f"{label} 학원 일정은 없어."
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines = [
        f"{label} 학원 일정 {len(rows)}건",
        (
            f"업무일정 {summary.get('work', 0)}건, 학원일정 {summary.get('academy', 0)}건, "
            f"휴일 {summary.get('holiday', 0)}건, 기타 {summary.get('other', 0)}건"
        ),
    ]
    for row in rows[:_MESSAGE_LIMIT]:
        title = row["title"] or "제목 없음"
        time_text = _time_text(row)
        lines.append(f"- {_short_date(row['date'])} {_event_label(row)}{time_text}: {title}")
    if len(rows) > _MESSAGE_LIMIT:
        lines.append(f"외 {len(rows) - _MESSAGE_LIMIT}건")
    return "\n".join(lines)


def _consultation_schedule_message(payload: dict[str, Any]) -> str:
    rows = [row for row in payload.get("consultations", []) if isinstance(row, dict)]
    label = _range_label(payload)
    if not rows:
        return f"{label} 신규 상담 일정은 없어."
    lines = [f"{label} 신규 상담 일정 {len(rows)}건"]
    for row in rows[:_MESSAGE_LIMIT]:
        profile = " ".join(item for item in [row["student_name"], row["student_grade"], row["student_school"]] if item)
        target = f" / 목표 {row['target_school']}" if row["target_school"] else ""
        status = f" / {row['status']}" if row["status"] else ""
        lines.append(f"- {_short_date(row['preferred_date'])} {_short_time(row['preferred_time'])}: {profile}{target}{status}")
    if len(rows) > _MESSAGE_LIMIT:
        lines.append(f"외 {len(rows) - _MESSAGE_LIMIT}건")
    return "\n".join(lines)


def _new_registration_only(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return False


def _range_label(payload: dict[str, Any]) -> str:
    start = str(payload.get("start_date") or "")
    end = str(payload.get("end_date") or "")
    return start if start == end else f"{start}~{end}"


def _short_date(value: str) -> str:
    return value[5:] if len(value) >= 10 else value


def _short_time(value: str) -> str:
    return value[:5] if len(value) >= 5 else value


def _time_text(row: dict[str, Any]) -> str:
    if row.get("is_all_day"):
        return ""
    start = _short_time(str(row.get("start_time") or ""))
    end = _short_time(str(row.get("end_time") or ""))
    if start and start != "00:00":
        return f" {start}~{end}" if end and end != "00:00" else f" {start}"
    return ""


def _event_label(row: dict[str, Any]) -> str:
    if row.get("is_holiday"):
        return "휴일"
    return {"work": "업무일정", "academy": "학원일정"}.get(str(row.get("event_type") or ""), "기타")


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


def _json_ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)
