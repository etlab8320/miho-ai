"""Read-only Peak class assignment lookup."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol


class AssignmentClient(Protocol):
    def get_peak_assignments(self, day: date, *, time_slot: str = "") -> dict[str, Any]: ...


def assignments_for_day(
    client: AssignmentClient,
    target_day: date,
    *,
    time_slot: str = "",
) -> dict[str, Any]:
    payload = client.get_peak_assignments(target_day, time_slot=time_slot)
    slots = _assignment_slots(payload)
    classes = [class_row for slot_rows in slots.values() for class_row in slot_rows["classes"]]
    waiting = [row for slot_rows in slots.values() for row in slot_rows["waiting_students"]]
    return {
        "date": str(payload.get("date") or target_day.isoformat()),
        "time_slot": time_slot,
        "summary": {
            "slots": len(slots),
            "classes": len(classes),
            "assigned_students": sum(len(row["students"]) for row in classes),
            "waiting_students": len(waiting),
        },
        "slots": slots,
    }


def _assignment_slots(payload: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    raw_slots = payload.get("slots") if isinstance(payload, dict) else {}
    if not isinstance(raw_slots, dict):
        return {}
    slots: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for slot, body in raw_slots.items():
        if not isinstance(body, dict):
            continue
        classes = [_class_row(row) for row in _dict_rows(body.get("classes"))]
        waiting = [_student_row(row) for row in _dict_rows(body.get("waitingStudents"))]
        classes = [row for row in classes if row["class_num"] or row["students"] or row["instructors"]]
        waiting = [row for row in waiting if row["student_name"]]
        if classes or waiting:
            slots[str(slot)] = {"classes": classes, "waiting_students": waiting}
    return slots


def _class_row(row: dict[str, Any]) -> dict[str, Any]:
    students = [_student_row(item) for item in _dict_rows(row.get("students"))]
    return {
        "class_num": _to_int(row.get("class_num") or row.get("classNumber")),
        "instructors": [_instructor_row(item) for item in _dict_rows(row.get("instructors"))],
        "students": [item for item in students if item["student_name"]],
    }


def _instructor_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "instructor_id": _to_int(row.get("id") or row.get("instructor_id")),
        "name": _text(row.get("name") or row.get("instructor_name")),
        "is_main": bool(row.get("isMain") or row.get("is_main")),
    }


def _student_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "assignment_id": _to_int(row.get("id")),
        "student_id": _to_int(row.get("student_id")),
        "student_name": _text(row.get("student_name") or row.get("name")),
        "school": _text(row.get("school")),
        "grade": _text(row.get("grade")),
        "gender": _text(row.get("gender")),
        "is_trial": bool(row.get("is_trial")),
        "attendance_status": _text(row.get("attendance_status")),
        "absence_reason": _text(row.get("absence_reason")),
    }


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
