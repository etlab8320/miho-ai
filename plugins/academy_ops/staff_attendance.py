"""Read-only PACA instructor attendance aggregation."""

from __future__ import annotations

from datetime import date
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


def _attendance_row(instructor: dict[str, Any], attendance: dict[str, Any]) -> dict[str, Any]:
    return {
        "instructor_id": _to_int(instructor.get("id")),
        "name": str(instructor.get("name") or ""),
        "instructor_type": str(instructor.get("instructor_type") or ""),
        "salary_type": str(instructor.get("salary_type") or ""),
        "work_date": str(attendance.get("work_date") or "")[:10],
        "time_slot": str(attendance.get("time_slot") or ""),
        "check_in_time": _time_text(attendance.get("check_in_time")),
        "check_out_time": _time_text(attendance.get("check_out_time")),
        "attendance_status": str(attendance.get("attendance_status") or "unknown"),
    }


def _time_text(value: Any) -> str:
    text = str(value or "").strip()
    return text[:8] if text else ""


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
