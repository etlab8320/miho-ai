"""Tool handlers for read-only PACA instructor attendance lookup."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from .academy_api import AcademyApiError
from .academy_query_tools import _resolve_client
from .response_guidance import academy_response_guidance
from .staff_attendance import staff_attendance_for_day, staff_attendance_for_range


def register_staff_attendance_tools(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_staff_attendance_day",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "조회 날짜. LLM이 해석한 YYYY-MM-DD 형식.",
                },
            },
            "required": ["date"],
            "additionalProperties": False,
        },
        handler=_staff_attendance_day_tool_handler,
        description=(
            "Return PACA instructor attendance for one day from live instructor attendance records. "
            "Use for teacher/staff/instructor work-attendance questions. "
            "Do not call with empty arguments; resolve natural-language dates to YYYY-MM-DD first."
        ),
    )
    ctx.register_tool(
        name="academy_staff_attendance_range",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "staff_query": {"type": "string", "description": "조회할 강사 이름. 전체면 빈 문자열."},
                "start_date": {"type": "string", "description": "조회 시작일. YYYY-MM-DD 형식."},
                "end_date": {"type": "string", "description": "조회 종료일. YYYY-MM-DD 형식."},
            },
            "required": ["start_date", "end_date"],
            "additionalProperties": False,
        },
        handler=_staff_attendance_range_tool_handler,
        description=(
            "Return PACA instructor attendance records for a date range, optionally filtered by instructor name. "
            "Use for monthly/weekly staff attendance counts, worked days, or a specific instructor's attendance history. "
            "For future scheduled work, use academy_staff_schedule_day instead."
        ),
    )


def _staff_attendance_day_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    target_day = _date_arg(payload.get("date"))
    if target_day is None:
        return _json_error("조회 날짜를 YYYY-MM-DD로 지정해줘.")
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        attendance = staff_attendance_for_day(client_or_error, target_day)
    except AcademyApiError as exc:
        return _json_error(str(exc))
    return _json_ok(
        {
            "operation": "staff.attendance_day",
            "date": attendance["date"],
            "summary": attendance["summary"],
            "instructors": attendance["instructors"],
            "message": _staff_attendance_message(attendance),
            "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
        }
    )


def _staff_attendance_range_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    start_day = _date_arg(payload.get("start_date"))
    end_day = _date_arg(payload.get("end_date"))
    if start_day is None or end_day is None:
        return _json_error("조회 기간을 start_date/end_date YYYY-MM-DD로 지정해줘.")
    staff_query = str(payload.get("staff_query") or "").strip()
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        attendance = staff_attendance_for_range(client_or_error, start_day, end_day, staff_query=staff_query)
    except AcademyApiError as exc:
        return _json_error(str(exc))
    return _json_ok(
        {
            "operation": "staff.attendance_range",
            "start_date": attendance["start_date"],
            "end_date": attendance["end_date"],
            "staff_query": attendance["staff_query"],
            "summary": attendance["summary"],
            "instructors": attendance["instructors"],
            "records": attendance["records"],
            "message": _staff_attendance_range_message(attendance),
            "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
        }
    )


def _staff_attendance_message(payload: dict[str, Any]) -> str:
    names = [row["name"] for row in payload["instructors"] if row.get("name")]
    if not names:
        return f"{payload['date']} 출근 기록이 있는 강사는 없어."
    return f"{payload['date']} 출근 강사: {', '.join(names)}."


def _staff_attendance_range_message(payload: dict[str, Any]) -> str:
    start = str(payload.get("start_date") or "")
    end = str(payload.get("end_date") or "")
    staff_query = str(payload.get("staff_query") or "").strip()
    instructors = payload.get("instructors") if isinstance(payload.get("instructors"), list) else []
    if staff_query and not instructors:
        return f"{staff_query} {start}~{end} 출근 기록은 없어."
    if staff_query and len(instructors) == 1:
        item = instructors[0]
        days = ", ".join(_short_dates(item.get("work_days")))
        suffix = f" 출근일: {days}" if days else ""
        return f"{item.get('name') or staff_query} {start}~{end} 출근 {item.get('worked', 0)}회.{suffix}"
    if not instructors:
        return f"{start}~{end} 출근 기록이 있는 강사는 없어."
    lines = [f"{start}~{end} 출근 강사 {len(instructors)}명"]
    for item in instructors:
        lines.append(f"{item.get('name')}: {item.get('worked', 0)}회")
    return "\n".join(lines)


def _short_dates(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value)[5:10].replace("-", "/") for value in values if str(value)]


def _date_arg(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


def _json_ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)
