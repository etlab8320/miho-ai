"""Structured response focus formatters for academy tool payloads."""

from __future__ import annotations

from datetime import date
from typing import Any


RESPONSE_FOCUSES = ("summary", "daily_attendance", "unchecked_dates")
STATUS_LABELS = {
    "present": "출석",
    "late": "지각",
    "absent": "결석",
    "unchecked": "미체크",
    "upcoming": "예정",
    "no_class": "수업없음",
    "excused": "인정결석",
    "makeup": "보강",
}
SLOT_LABELS = {"morning": "오전반", "afternoon": "오후반", "evening": "저녁반"}
WEEKDAY_LABELS = ("월", "화", "수", "목", "금", "토", "일")


def focused_response(payload: dict[str, Any], response_focus: str) -> str:
    if response_focus not in RESPONSE_FOCUSES:
        return ""
    if response_focus == "daily_attendance":
        return _daily_attendance_response(payload)
    if response_focus == "unchecked_dates":
        return _filtered_attendance_response(payload, "unchecked", "미체크")
    return ""


def _daily_attendance_response(payload: dict[str, Any]) -> str:
    rows = _attendance_rows(payload)
    if not rows:
        return ""
    lines = [_attendance_title(payload)]
    for row in rows:
        lines.append(_attendance_line(row))
    return "\n".join(lines)


def _filtered_attendance_response(payload: dict[str, Any], status: str, label: str) -> str:
    rows = [row for row in _attendance_rows(payload) if str(row.get("status") or "") == status]
    student_name = _student_name(payload)
    if not rows:
        return f"{student_name} {label} 날짜는 없어."
    lines = [f"{student_name} {label} 날짜 {len(rows)}일"]
    for row in rows:
        lines.append(_attendance_line(row))
    return "\n".join(lines)


def _attendance_title(payload: dict[str, Any]) -> str:
    start = str(payload.get("start_date") or "")
    end = str(payload.get("end_date") or "")
    return f"{_student_name(payload)} 출석 {start}~{end}".strip()


def _attendance_line(row: dict[str, Any]) -> str:
    day = str(row.get("date") or "")
    label = STATUS_LABELS.get(str(row.get("status") or ""), str(row.get("status") or ""))
    parts = [f"{_short_day(day)} {_weekday(day)}: {label}"]
    slot = SLOT_LABELS.get(str(row.get("time_slot") or ""), str(row.get("time_slot") or ""))
    if slot:
        parts.append(slot)
    reason = str(row.get("absence_reason") or "").strip()
    if reason:
        parts.append(reason)
    return " / ".join(parts)


def _attendance_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("attendance")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _student_name(payload: dict[str, Any]) -> str:
    student = payload.get("student") if isinstance(payload.get("student"), dict) else {}
    return str(student.get("name") or "학생")


def _short_day(value: str) -> str:
    return value[5:10].replace("-", "/") if len(value) >= 10 else value


def _weekday(value: str) -> str:
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return ""
    return WEEKDAY_LABELS[parsed.weekday()]
