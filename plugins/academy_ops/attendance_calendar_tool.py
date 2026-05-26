"""Tool entrypoint for student attendance calendar images."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any
from zoneinfo import ZoneInfo

from .academy_api import AcademyApiError
from .academy_query_tools import _resolve_client
from .attendance_calendar_renderer import AttendanceCalendarImageRenderer, AttendanceCalendarRenderError
from .response_guidance import academy_response_guidance
from .student_attendance import StudentAttendanceError, student_attendance_range


def _student_attendance_calendar_image_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    student_query = str(payload.get("student_query") or "").strip()
    date_range = _date_range(payload)
    if isinstance(date_range, str):
        return _json_error(date_range)
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    renderer = kwargs.get("renderer") or AttendanceCalendarImageRenderer()
    today = _date_arg(payload.get("today")) or _today_date()
    try:
        attendance = student_attendance_range(client_or_error, student_query, date_range[0], date_range[1], today=today)
        attendance["today"] = today.isoformat()
        image_path = renderer.render(attendance)
    except (AcademyApiError, StudentAttendanceError, AttendanceCalendarRenderError) as exc:
        return _json_error(str(exc))
    name = str(attendance.get("student", {}).get("name") or "학생")
    media_tag = f"MEDIA:{image_path}"
    message = f"{name} 출석 달력이야. 수업없는 날은 표시하지 않았어. {media_tag}"
    return _json_ok(
        {
            "operation": "attendance.student_calendar_image",
            **attendance,
            "message": message,
            "image_path": str(image_path),
            "media_tag": media_tag,
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


def _today_date() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


def _json_ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)
