"""Read-only PACA instructor attendance aggregation."""

from __future__ import annotations

from datetime import date
from calendar import monthrange
from typing import Any, Protocol


class StaffAttendanceClient(Protocol):
    def list_paca_instructors(self, *, status: str = "active") -> list[dict[str, Any]]: ...

    def get_paca_instructor_attendance(
        self,
        instructor_id: int,
        *,
        year: int,
        month: int,
    ) -> list[dict[str, Any]]: ...


def staff_attendance_for_day(
    client: StaffAttendanceClient,
    target_day: date,
) -> dict[str, Any]:
    rows = []
    instructors = client.list_paca_instructors(status="active")
    for instructor in instructors:
        instructor_id = _to_int(instructor.get("id"))
        if not instructor_id:
            continue
        attendances = client.get_paca_instructor_attendance(
            instructor_id,
            year=target_day.year,
            month=target_day.month,
        )
        for attendance in attendances:
            if str(attendance.get("work_date") or "")[:10] != target_day.isoformat():
                continue
            rows.append(_attendance_row(instructor, attendance))

    rows.sort(key=lambda row: (row["time_slot"], row["name"]))
    present_rows = [row for row in rows if row["attendance_status"] in {"present", "late"}]
    return {
        "date": target_day.isoformat(),
        "summary": {
            "active_instructors": len(instructors),
            "worked": len(present_rows),
            "records": len(rows),
        },
        "instructors": present_rows,
        "all_records": rows,
    }


def staff_attendance_for_range(
    client: StaffAttendanceClient,
    start_day: date,
    end_day: date,
    *,
    staff_query: str = "",
) -> dict[str, Any]:
    if end_day < start_day:
        start_day, end_day = end_day, start_day
    instructors = client.list_paca_instructors(status="active")
    matched = _matched_instructors(instructors, staff_query)
    rows = []
    for instructor in matched:
        instructor_id = _to_int(instructor.get("id"))
        if not instructor_id:
            continue
        for year, month in _months_between(start_day, end_day):
            attendances = client.get_paca_instructor_attendance(instructor_id, year=year, month=month)
            for attendance in attendances:
                work_day = _date_text(attendance.get("work_date"))
                if not work_day or not (start_day.isoformat() <= work_day <= end_day.isoformat()):
                    continue
                row = _attendance_row(instructor, attendance)
                if row["attendance_status"] in {"present", "late"}:
                    rows.append(row)

    rows.sort(key=lambda row: (row["work_date"], row["time_slot"], row["name"]))
    return {
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "staff_query": staff_query,
        "summary": {
            "active_instructors": len(instructors),
            "matched_instructors": len(matched),
            "worked": len(rows),
            "work_days": len({row["work_date"] for row in rows}),
        },
        "instructors": _instructor_summaries(rows),
        "records": rows,
    }


def _attendance_row(instructor: dict[str, Any], attendance: dict[str, Any]) -> dict[str, Any]:
    return {
        "instructor_id": _to_int(instructor.get("id")),
        "name": str(instructor.get("name") or ""),
        "instructor_type": str(instructor.get("instructor_type") or ""),
        "salary_type": str(instructor.get("salary_type") or ""),
        "work_date": _date_text(attendance.get("work_date")),
        "time_slot": str(attendance.get("time_slot") or ""),
        "check_in_time": _time_text(attendance.get("check_in_time")),
        "check_out_time": _time_text(attendance.get("check_out_time")),
        "attendance_status": str(attendance.get("attendance_status") or "unknown"),
    }


def _matched_instructors(instructors: list[dict[str, Any]], staff_query: str) -> list[dict[str, Any]]:
    query = _compact(staff_query)
    if not query:
        return instructors
    return [row for row in instructors if query in _compact(row.get("name"))]


def _months_between(start_day: date, end_day: date) -> list[tuple[int, int]]:
    cursor = date(start_day.year, start_day.month, 1)
    end_month = date(end_day.year, end_day.month, 1)
    result = []
    while cursor <= end_month:
        result.append((cursor.year, cursor.month))
        last = monthrange(cursor.year, cursor.month)[1]
        cursor = cursor.replace(day=last) + date.resolution
    return result


def _instructor_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: dict[int, dict[str, Any]] = {}
    for row in rows:
        instructor_id = _to_int(row.get("instructor_id"))
        if not instructor_id:
            continue
        item = summaries.setdefault(
            instructor_id,
            {
                "instructor_id": instructor_id,
                "name": row.get("name", ""),
                "worked": 0,
                "work_days": [],
            },
        )
        item["worked"] += 1
        day = str(row.get("work_date") or "")
        if day and day not in item["work_days"]:
            item["work_days"].append(day)
    return sorted(summaries.values(), key=lambda item: str(item.get("name") or ""))


def _date_text(value: Any) -> str:
    return str(value or "")[:10]


def _compact(value: Any) -> str:
    return "".join(str(value or "").lower().split())


def _time_text(value: Any) -> str:
    text = str(value or "").strip()
    return text[:8] if text else ""


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
