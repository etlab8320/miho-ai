"""Read-only PACA academy schedule and consultation aggregation."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol


class AcademyCalendarClient(Protocol):
    def get_paca_academy_events(self, start_day: date, end_day: date) -> list[dict[str, Any]]: ...

    def list_paca_consultations(self) -> list[dict[str, Any]]: ...


def academy_schedules_for_range(
    client: AcademyCalendarClient,
    start_day: date,
    end_day: date,
) -> dict[str, Any]:
    rows = [_schedule_row(row) for row in client.get_paca_academy_events(start_day, end_day)]
    rows = [row for row in rows if start_day.isoformat() <= row["date"] <= end_day.isoformat()]
    rows.sort(key=lambda row: (row["date"], row["start_time"], row["id"]))
    return {
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "summary": _event_summary(rows),
        "schedules": rows,
    }


def consultation_schedules_for_range(
    client: AcademyCalendarClient,
    start_day: date,
    end_day: date,
    *,
    new_registration_only: bool = True,
) -> dict[str, Any]:
    rows = [
        _consultation_row(row)
        for row in client.list_paca_consultations()
        if _is_consultation_in_range(row, start_day, end_day)
    ]
    if new_registration_only:
        rows = [row for row in rows if row["consultation_type"] == "new_registration"]
    rows = [row for row in rows if row["status"] != "cancelled"]
    rows.sort(key=lambda row: (row["preferred_date"], row["preferred_time"], row["id"]))
    return {
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "new_registration_only": new_registration_only,
        "summary": {"total": len(rows), "confirmed": _count_status(rows, "confirmed")},
        "consultations": rows,
    }


def _schedule_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _to_int(row.get("id")),
        "date": str(row.get("event_date") or row.get("date") or ""),
        "event_type": str(row.get("event_type") or "other"),
        "title": str(row.get("title") or ""),
        "description": str(row.get("description") or ""),
        "start_time": str(row.get("start_time") or ""),
        "end_time": str(row.get("end_time") or ""),
        "is_all_day": bool(row.get("is_all_day")),
        "is_holiday": bool(row.get("is_holiday")),
        "created_by_name": str(row.get("created_by_name") or ""),
    }


def _consultation_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _to_int(row.get("id")),
        "consultation_type": str(row.get("consultation_type") or ""),
        "learning_type": str(row.get("learning_type") or ""),
        "student_name": str(row.get("student_name") or ""),
        "student_grade": str(row.get("student_grade") or ""),
        "student_school": str(row.get("student_school") or ""),
        "target_school": str(row.get("target_school") or ""),
        "preferred_date": str(row.get("preferred_date") or ""),
        "preferred_time": str(row.get("preferred_time") or ""),
        "status": str(row.get("status") or ""),
        "referral_sources": _str_list(row.get("referral_sources")),
    }


def _is_consultation_in_range(row: dict[str, Any], start_day: date, end_day: date) -> bool:
    preferred_date = str(row.get("preferred_date") or "")
    return start_day.isoformat() <= preferred_date <= end_day.isoformat()


def _event_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"total": len(rows), "work": 0, "academy": 0, "holiday": 0, "other": 0}
    for row in rows:
        if row.get("is_holiday"):
            summary["holiday"] += 1
            continue
        event_type = str(row.get("event_type") or "other")
        if event_type in {"work", "academy"}:
            summary[event_type] += 1
        else:
            summary["other"] += 1
    return summary


def _count_status(rows: list[dict[str, Any]], status: str) -> int:
    return sum(1 for row in rows if row.get("status") == status)


def _str_list(value: Any) -> list[str]:
    return [str(item) for item in value if item] if isinstance(value, list) else []


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
