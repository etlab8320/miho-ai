"""Read-only student attendance lookup across a date range."""

from __future__ import annotations

from datetime import date, timedelta
import json
from typing import Any, Protocol

from .student_lookup import StudentLookupAmbiguous, StudentLookupNotFound, resolve_paca_student


PACA_WEEKDAY_TO_PYTHON = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
TIME_SLOT_ORDER = {"morning": 0, "afternoon": 1, "evening": 2}


class StudentAttendanceClient(Protocol):
    def search_paca_students(self, query: str) -> list[dict[str, Any]]: ...

    def get_paca_student_attendance(self, paca_student_id: int, *, year_month: str) -> dict[str, Any]: ...


class StudentAttendanceError(RuntimeError):
    pass


def student_attendance_range(
    client: StudentAttendanceClient,
    student_query: str,
    start_day: date,
    end_day: date,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    if end_day < start_day:
        raise StudentAttendanceError("조회 종료일이 시작일보다 빠를 수는 없어.")
    reference_day = today or date.today()
    paca_student = _resolve_student(client, student_query)
    paca_student_id = _to_int(paca_student.get("id"))
    attendance_rows = _paca_attendance_rows_by_day(client, paca_student_id, start_day, end_day)
    schedule_slots, schedule_known = _schedule_baseline(client, paca_student, start_day, end_day)
    rows = [
        _day_row(
            start_day + timedelta(days=offset),
            attendance_rows,
            schedule_slots,
            schedule_known,
            reference_day,
        )
        for offset in range((end_day - start_day).days + 1)
    ]
    summary = _summary(rows)
    return {
        "student": {
            "paca_student_id": paca_student_id,
            "name": str(paca_student.get("name") or ""),
            "school": str(paca_student.get("school") or ""),
            "grade": str(paca_student.get("grade") or ""),
        },
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "summary": summary,
        "attendance": rows,
        "absence_dates": [row["date"] for row in rows if row["status"] == "absent"],
        "late_dates": [row["date"] for row in rows if row["status"] == "late"],
    }


def _resolve_student(client: StudentAttendanceClient, query: str) -> dict[str, Any]:
    if not query.strip():
        raise StudentAttendanceError("학생 이름이나 검색어를 알려줘.")
    try:
        return resolve_paca_student(client, query)
    except StudentLookupNotFound as exc:
        raise StudentAttendanceError("학생을 찾지 못했어. 이름이나 학교를 조금 더 정확히 알려줘.")
    except StudentLookupAmbiguous as exc:
        raise StudentAttendanceError(f"동명이인이 있어. 학생을 조금 더 구체적으로 골라줘: {exc}") from exc


def _day_row(
    day: date,
    attendance_rows: dict[str, dict[str, Any]],
    schedule_slots: dict[str, set[str]],
    schedule_known: bool,
    today: date,
) -> dict[str, Any]:
    row = attendance_rows.get(day.isoformat())
    if row:
        status = _status(row)
        if status == "present" and bool(row.get("is_makeup")):
            status = "makeup"
        if status == "unchecked" and day >= today:
            status = "upcoming"
        return {
            "date": day.isoformat(),
            "status": status,
            "time_slot": str(row.get("time_slot") or ""),
            "absence_reason": str(row.get("notes") or row.get("absence_reason") or ""),
            "scheduled": True,
            "is_makeup": bool(row.get("is_makeup")),
        }
    slots = schedule_slots.get(day.isoformat(), set())
    if schedule_known and not slots:
        return {"date": day.isoformat(), "status": "no_class", "time_slot": "", "absence_reason": "", "scheduled": False}
    if day >= today:
        return {
            "date": day.isoformat(),
            "status": "upcoming",
            "time_slot": _join_slots(slots),
            "absence_reason": "",
            "scheduled": bool(slots),
        }
    return {
        "date": day.isoformat(),
        "status": "unchecked",
        "time_slot": _join_slots(slots),
        "absence_reason": "",
        "scheduled": bool(slots),
    }


def _schedule_baseline(
    client: StudentAttendanceClient,
    student: dict[str, Any],
    start_day: date,
    end_day: date,
) -> tuple[dict[str, set[str]], bool]:
    has_student_class_days = bool(_class_days(student.get("class_days")))
    student_slots = _student_class_slots(student, start_day, end_day)
    academy_slots = _academy_schedule_slots(client, start_day, end_day)
    if academy_slots is None:
        return student_slots, bool(student_slots)
    if not student_slots:
        if has_student_class_days:
            return {day: set() for day in _date_keys(start_day, end_day)}, True
        return academy_slots, True
    return {_day_key: academy_slots.get(_day_key, set()) & slots for _day_key, slots in student_slots.items()}, True


def _student_class_slots(student: dict[str, Any], start_day: date, end_day: date) -> dict[str, set[str]]:
    class_days = _class_days(student.get("class_days"))
    if not class_days:
        return {}
    slots_by_day: dict[str, set[str]] = {}
    fallback_slot = str(student.get("time_slot") or "")
    for day in _days(start_day, end_day):
        slots = {
            _class_day_slot(item, fallback_slot)
            for item in class_days
            if PACA_WEEKDAY_TO_PYTHON.get(_to_int(item.get("day"))) == day.weekday()
        }
        slots.discard("")
        if slots:
            slots_by_day[day.isoformat()] = slots
    return slots_by_day


def _class_day_slot(item: dict[str, Any], fallback_slot: str) -> str:
    return str(item.get("timeSlot") or item.get("time_slot") or item.get("slot") or fallback_slot)


def _academy_schedule_slots(
    client: StudentAttendanceClient,
    start_day: date,
    end_day: date,
) -> dict[str, set[str]] | None:
    list_schedules = getattr(client, "list_paca_schedules", None)
    if not callable(list_schedules):
        return None
    slots_by_day: dict[str, set[str]] = {}
    for row in list_schedules(start_day, end_day):
        day = str(row.get("class_date") or row.get("date") or "")[:10]
        if day < start_day.isoformat() or day > end_day.isoformat():
            continue
        if not _has_scheduled_students(row):
            continue
        slot = str(row.get("time_slot") or row.get("slot") or "")
        if slot:
            slots_by_day.setdefault(day, set()).add(slot)
    return slots_by_day


def _class_days(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if not isinstance(value, list):
        return []
    days: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            days.append(item)
        elif isinstance(item, int):
            days.append({"day": item})
    return days


def _has_scheduled_students(row: dict[str, Any]) -> bool:
    if "student_count" not in row and "trial_count" not in row:
        return True
    return _to_int(row.get("student_count")) + _to_int(row.get("trial_count")) > 0


def _paca_attendance_rows_by_day(
    client: StudentAttendanceClient,
    paca_student_id: int,
    start_day: date,
    end_day: date,
) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for year_month in _year_months(start_day, end_day):
        payload = client.get_paca_student_attendance(paca_student_id, year_month=year_month)
        records = payload.get("records") if isinstance(payload, dict) else None
        for row in records or []:
            if not isinstance(row, dict):
                continue
            day = str(row.get("date") or "")[:10]
            if start_day.isoformat() <= day <= end_day.isoformat():
                rows[day] = row
    return rows


def _status(row: dict[str, Any]) -> str:
    value = str(row.get("attendance_status") or row.get("status") or "").strip()
    return value if value in {"present", "late", "absent", "excused", "makeup"} else "unchecked"


def _summary(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    counts = {
        "present": 0,
        "late": 0,
        "absent": 0,
        "excused": 0,
        "makeup": 0,
        "unchecked": 0,
        "upcoming": 0,
        "no_class": 0,
    }
    for row in rows:
        status = row["status"] if row["status"] in counts else "unchecked"
        counts[status] += 1
    checked = counts["present"] + counts["late"] + counts["absent"] + counts["excused"] + counts["makeup"]
    scheduled = checked + counts["unchecked"] + counts["upcoming"]
    attended = counts["present"] + counts["late"] + counts["makeup"]
    attendance_rate = round((attended / checked) * 100, 1) if checked else 0.0
    return {**counts, "checked": checked, "scheduled": scheduled, "attendance_rate": attendance_rate}


def _days(start_day: date, end_day: date) -> list[date]:
    return [start_day + timedelta(days=offset) for offset in range((end_day - start_day).days + 1)]


def _date_keys(start_day: date, end_day: date) -> list[str]:
    return [day.isoformat() for day in _days(start_day, end_day)]


def _join_slots(slots: set[str]) -> str:
    return ", ".join(sorted(slots, key=lambda value: (TIME_SLOT_ORDER.get(value, 99), value)))


def _year_months(start_day: date, end_day: date) -> list[str]:
    months: list[str] = []
    cursor = date(start_day.year, start_day.month, 1)
    last = date(end_day.year, end_day.month, 1)
    while cursor <= last:
        months.append(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return months


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
