"""Read-only PACA class-schedule roster aggregation (who attends class today)."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

TIME_SLOT_ORDER = {"morning": 0, "afternoon": 1, "evening": 2}


class ClassRosterClient(Protocol):
    def list_paca_schedules(self, start_day: date, end_day: date) -> list[dict[str, Any]]: ...

    def get_paca_schedule_attendance(self, schedule_id: int) -> dict[str, Any]: ...


def class_roster_for_range(
    client: ClassRosterClient,
    start_day: date,
    end_day: date,
    *,
    with_roster: bool = True,
) -> dict[str, Any]:
    schedules = [
        _schedule_row(row)
        for row in client.list_paca_schedules(start_day, end_day)
        if start_day.isoformat() <= _schedule_date(row) <= end_day.isoformat()
    ]
    schedules.sort(key=lambda row: (row["date"], TIME_SLOT_ORDER.get(row["time_slot"], 99), row["id"]))
    if with_roster:
        for schedule in schedules:
            schedule["students"] = _roster_for_schedule(client, schedule["id"])
    return {
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "summary": _summary(schedules, with_roster=with_roster),
        "schedules": schedules,
    }


def _roster_for_schedule(client: ClassRosterClient, schedule_id: int) -> list[dict[str, Any]]:
    if schedule_id <= 0:
        return []
    payload = client.get_paca_schedule_attendance(schedule_id)
    students = payload.get("students") if isinstance(payload, dict) else None
    rows = [_student_row(row) for row in students or [] if isinstance(row, dict)]
    rows = [row for row in rows if row["name"]]
    rows.sort(key=lambda row: (not row["is_trial"], row["name"]))
    return rows


def _schedule_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _to_int(row.get("id")),
        "date": _schedule_date(row),
        "time_slot": str(row.get("time_slot") or row.get("slot") or ""),
        "title": str(row.get("title") or ""),
        "instructor_name": str(row.get("instructor_name") or ""),
        "attendance_taken": bool(row.get("attendance_taken")),
        "student_count": _to_int(row.get("student_count")),
        "trial_count": _to_int(row.get("trial_count")),
    }


def _student_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "student_id": _to_int(row.get("student_id")),
        "name": str(row.get("student_name") or row.get("name") or "").strip(),
        "school": str(row.get("school") or "").strip(),
        "grade": str(row.get("grade") or "").strip(),
        "is_trial": bool(row.get("is_trial")),
        "is_makeup": bool(row.get("is_makeup")),
        "attendance_status": str(row.get("attendance_status") or "").strip(),
    }


def _summary(schedules: list[dict[str, Any]], *, with_roster: bool) -> dict[str, int]:
    summary = {"classes": len(schedules), "students": 0, "trial": 0}
    for schedule in schedules:
        if with_roster:
            students = schedule.get("students") if isinstance(schedule.get("students"), list) else []
            summary["students"] += len(students)
            summary["trial"] += sum(1 for student in students if student.get("is_trial"))
        else:
            summary["students"] += _to_int(schedule.get("student_count"))
            summary["trial"] += _to_int(schedule.get("trial_count"))
    return summary


def _schedule_date(row: dict[str, Any]) -> str:
    return str(row.get("class_date") or row.get("date") or "")[:10]


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
