"""Read-only Peak student performance record lookup."""

from __future__ import annotations

from datetime import date, timedelta
import json
import re
from typing import Any

from .academy_api import AcademyApiError
from .academy_query_tools import _date_arg, _int_arg, _json_error, _json_ok, _resolve_client
from .response_guidance import academy_response_guidance
from .student_lookup import StudentLookupAmbiguous, StudentLookupNotFound, resolve_paca_student


def register_student_records_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_student_record_lookup",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_query": {"type": "string", "description": "학생 이름, 학교, 또는 PACA 검색어."},
                "event_query": {"type": "string", "description": "조회할 실기 종목명 또는 측정 항목명."},
                "date": {"type": "string", "description": "특정 측정일. YYYY-MM-DD 형식."},
                "today": {"type": "string", "description": "기준일. YYYY-MM-DD 형식."},
                "period_days": {"type": "integer", "minimum": 1, "maximum": 180, "default": 30},
            },
            "required": ["student_query"],
            "additionalProperties": False,
        },
        handler=_student_record_lookup_tool_handler,
        description=(
            "Return read-only Peak practical-test records for ONE student over time (개인 학생의 실기 기록). "
            "Use for a single student's measurement / practical-test / event / performance history. "
            "For a whole 월말테스트 cohort (all participants, 남녀 평균, rankings, school filters), "
            "use academy_monthly_test_records instead — NOT this tool. "
            "Do not use attendance, staff attendance, or workout-plan tools for student performance records."
        ),
    )


def _student_record_lookup_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    query = str(payload.get("student_query") or "").strip()
    if not query:
        return _json_error("기록을 조회할 학생 이름이나 검색어를 알려줘.")
    event_query = str(payload.get("event_query") or "").strip()
    target_day = _date_arg(payload.get("date"))
    today = _date_arg(payload.get("today")) or date.today()
    period_days = _int_arg(payload.get("period_days"), default=30, maximum=180)
    fallback_recent = bool(payload.get("fallback_recent_when_empty"))
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        student = resolve_paca_student(client_or_error, query)
        peak_student = _peak_student_for_paca(client_or_error.list_peak_students(), int(student.get("id") or 0))
        if peak_student is None:
            return _json_error(f"{_student_name(student)} Peak 학생 매핑을 찾지 못했어.")
        rows = client_or_error.list_peak_records(int(peak_student.get("id") or 0))
    except StudentLookupNotFound:
        return _json_error("학생을 찾지 못했어. 이름이나 학교를 조금 더 정확히 알려줘.")
    except StudentLookupAmbiguous as exc:
        return _json_error(f"동명이인이 있어. 학생을 조금 더 구체적으로 골라줘: {exc}")
    except (AcademyApiError, ValueError) as exc:
        return _json_error(str(exc))
    records = _filtered_records(rows, event_query=event_query, target_day=target_day, today=today, period_days=period_days)
    used_target_day = target_day
    if fallback_recent and target_day and not records:
        records = _filtered_records(rows, event_query=event_query, target_day=None, today=today, period_days=period_days)
        used_target_day = None
    student_name = _student_name(student)
    return _json_ok(
        {
            "operation": "student.record_lookup",
            "student": {
                "paca_student_id": int(student.get("id") or 0),
                "peak_student_id": int(peak_student.get("id") or 0),
                "name": student_name,
            },
            "event_query": event_query,
            "date": used_target_day.isoformat() if used_target_day else "",
            "period_days": period_days if used_target_day is None else 1,
            "records": records,
            "message": _message(
                student_name, records, event_query=event_query, target_day=used_target_day, period_days=period_days
            ),
            "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
        }
    )


def _peak_student_for_paca(students: list[dict[str, Any]], paca_student_id: int) -> dict[str, Any] | None:
    for student in students:
        if int(student.get("paca_student_id") or 0) == paca_student_id:
            return student
    return None


def _filtered_records(
    rows: list[dict[str, Any]],
    *,
    event_query: str,
    target_day: date | None,
    today: date,
    period_days: int,
) -> list[dict[str, Any]]:
    first_day = today - timedelta(days=max(1, period_days) - 1)
    records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        measured_day = _record_day(row.get("measured_at"))
        if target_day and measured_day != target_day:
            continue
        if target_day is None and measured_day and not (first_day <= measured_day <= today):
            continue
        if event_query and not _event_matches(event_query, str(row.get("record_type_name") or "")):
            continue
        value = _float_or_none(row.get("value"))
        if value is None:
            continue
        records.append(
            {
                "event_name": str(row.get("record_type_name") or "기록"),
                "measured_at": str(row.get("measured_at") or ""),
                "value": value,
                "unit": str(row.get("unit") or ""),
                "direction": str(row.get("direction") or ""),
            }
        )
    records.sort(key=lambda item: item["measured_at"], reverse=True)
    return records[:20]


def _event_matches(query: str, event_name: str) -> bool:
    needle = _compact(query)
    haystack = _compact(event_name)
    return bool(needle and (needle in haystack or _is_ordered_subsequence(needle, haystack)))


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _is_ordered_subsequence(needle: str, haystack: str) -> bool:
    cursor = 0
    for char in haystack:
        if cursor < len(needle) and needle[cursor] == char:
            cursor += 1
    return cursor == len(needle)


def _message(
    student_name: str,
    records: list[dict[str, Any]],
    *,
    event_query: str,
    target_day: date | None,
    period_days: int,
) -> str:
    label = event_query or "실기"
    when = target_day.isoformat() if target_day else "최근"
    if not records:
        # State the window explicitly so the user knows it's "not in the last
        # N days" — not "never". (Records like 윗몸일으키기 are measured rarely,
        # so an empty 30-day window is normal, not a failure.)
        if target_day:
            return f"{student_name} {target_day.isoformat()} {label} 기록은 없어."
        return (
            f"{student_name} 최근 {period_days}일간 {label} 기록은 없어 — 이 기간에 측정된 게 없어. "
            f"더 예전 기록까지 보려면 기간을 늘려서(예: 최근 1년) 다시 물어봐줘."
        )
    lines = [f"{student_name} {when} {label} 기록"]
    for row in records[:8]:
        value = f"{row['value']:g}{row['unit']}"
        lines.append(f"- {row['measured_at']}: {row['event_name']} {value}")
    return "\n".join(lines)


def _student_name(student: dict[str, Any]) -> str:
    return str(student.get("name") or "학생")


def _record_day(value: Any) -> date | None:
    text = str(value or "")
    return _date_arg(text[:10])


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
