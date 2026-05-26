"""Tool registration for student attendance range lookup."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any
from zoneinfo import ZoneInfo

from .academy_api import AcademyApiError
from .academy_query_tools import _resolve_client
from .response_guidance import academy_response_guidance
from .student_attendance import StudentAttendanceError, student_attendance_range


def _student_attendance_range_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    student_query = str(payload.get("student_query") or "").strip()
    date_range = _date_range(payload)
    if isinstance(date_range, str):
        return _json_error(date_range)
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    today = _date_arg(payload.get("today")) or _today()
    try:
        attendance = student_attendance_range(client_or_error, student_query, date_range[0], date_range[1], today=today)
        attendance["today"] = today.isoformat()
    except (AcademyApiError, StudentAttendanceError) as exc:
        return _json_error(str(exc))
    message = _message(attendance)
    return _json_ok(
        {
            "operation": "attendance.student_month",
            **attendance,
            "message": message,
            "assistant_guidance": {
                **academy_response_guidance(use_message_as_facts=True),
                "unchecked_label": "미체크",
                "do_not_use_labels": ["미확인"],
            },
        }
    )


def register_student_attendance_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_student_attendance_range",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_query": {"type": "string", "description": "학생 이름, 학교, 또는 PACA 검색어."},
                "start_date": {"type": "string", "description": "조회 시작일. YYYY-MM-DD 형식."},
                "end_date": {"type": "string", "description": "조회 종료일. YYYY-MM-DD 형식."},
                "today": {"type": "string", "description": "기준일. 보통 라우터 기준일이며 YYYY-MM-DD 형식."},
            },
            "required": ["student_query", "start_date", "end_date"],
            "additionalProperties": False,
        },
        handler=_student_attendance_range_tool_handler,
        description=(
            "Return safe PACA attendance history for one student over an explicit date range. "
            "The assistant must resolve natural-language periods into start_date/end_date first. "
            "Do not call with empty date arguments. "
            "After this tool returns, answer with the returned message field exactly unless the user "
            "explicitly asks for extra analysis. Use the Korean label '미체크' for unchecked days, "
            "not '미확인'."
        ),
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


def _message(payload: dict[str, Any]) -> str:
    student = payload.get("student") if isinstance(payload.get("student"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    name = str(student.get("name") or "학생")
    lines = [
        (
            f"{name} 출석 조회 {payload['start_date']}~{payload['end_date']}: "
            f"출석 {summary.get('present', 0)}회, 지각 {summary.get('late', 0)}회, "
            f"결석 {summary.get('absent', 0)}회, 미체크 {summary.get('unchecked', 0)}회, "
            f"수업없음 {summary.get('no_class', 0)}일"
        ),
        f"확인된 수업일 {summary.get('checked', 0)}일 기준 출석률 {summary.get('attendance_rate', 0)}%",
    ]
    if payload.get("absence_dates"):
        lines.append(f"결석일: {', '.join(payload['absence_dates'])}")
    if payload.get("late_dates"):
        lines.append(f"지각일: {', '.join(payload['late_dates'])}")
    upcoming = _to_int(summary.get("upcoming"))
    if upcoming:
        lines.append(f"예정 수업일 {upcoming}일은 아직 출결 판단에서 제외했어.")
    return "\n".join(lines)


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


def _json_ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)
