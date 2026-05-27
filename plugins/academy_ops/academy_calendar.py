"""Read-only PACA academy schedule and consultation aggregation."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Protocol


class AcademyCalendarClient(Protocol):
    def get_paca_academy_events(self, start_day: date, end_day: date) -> list[dict[str, Any]]: ...

    def list_paca_consultations(self) -> list[dict[str, Any]]: ...

    def get_peak_attendance(self, day: date) -> dict[str, Any]: ...


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
    trial_only: bool = False,
) -> dict[str, Any]:
    if trial_only:
        rows = _trial_attendance_rows(client, start_day, end_day)
        if not rows:
            rows = [
                _consultation_row(row)
                for row in client.list_paca_consultations()
                if _is_consultation_in_range(row, start_day, end_day)
            ]
            rows = [row for row in rows if _is_trial_consultation(row)]
    else:
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
        "trial_only": trial_only,
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
        "time_slot": str(row.get("time_slot") or ""),
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


def _is_trial_consultation(row: dict[str, Any]) -> bool:
    fields = (
        row.get("consultation_type"),
        row.get("learning_type"),
        row.get("matched_student_status"),
    )
    return any(_contains_trial_marker(value) for value in fields) or _truthy(row.get("linked_student_is_trial"))


def _trial_attendance_rows(
    client: AcademyCalendarClient,
    start_day: date,
    end_day: date,
) -> list[dict[str, Any]]:
    get_peak_attendance = getattr(client, "get_peak_attendance", None)
    if not callable(get_peak_attendance):
        return []
    rows: list[dict[str, Any]] = []
    for day in _days(start_day, end_day):
        payload = get_peak_attendance(day)
        for slot, student in _attendance_slot_rows(payload):
            if not _truthy(student.get("is_trial")):
                continue
            rows.append(
                {
                    "id": _to_int(student.get("assignment_id") or student.get("id") or student.get("student_id")),
                    "consultation_type": "trial_class",
                    "learning_type": "trial",
                    "student_name": str(student.get("student_name") or student.get("name") or "").strip(),
                    "student_grade": str(student.get("grade") or "").strip(),
                    "student_school": str(student.get("school") or "").strip(),
                    "target_school": "",
                    "preferred_date": str(payload.get("date") or day.isoformat())[:10],
                    "preferred_time": "",
                    "status": str(student.get("attendance_status") or "scheduled"),
                    "time_slot": str(slot),
                    "referral_sources": [],
                }
            )
    return [row for row in rows if row["student_name"]]


def _days(start_day: date, end_day: date) -> list[date]:
    count = (end_day - start_day).days + 1
    return [start_day + timedelta(days=offset) for offset in range(max(count, 0))]


def _attendance_slot_rows(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    slots = payload.get("slots") if isinstance(payload, dict) else {}
    if not isinstance(slots, dict):
        return []
    rows: list[tuple[str, dict[str, Any]]] = []
    for slot, raw_rows in slots.items():
        if not isinstance(raw_rows, list):
            continue
        rows.extend((str(slot), row) for row in raw_rows if isinstance(row, dict))
    return rows


def _contains_trial_marker(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in ("trial", "체험", "무료"))


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _str_list(value: Any) -> list[str]:
    return [str(item) for item in value if item] if isinstance(value, list) else []


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
