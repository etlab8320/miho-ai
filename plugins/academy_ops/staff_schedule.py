"""Read-only Peak instructor schedule aggregation."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol


class StaffScheduleClient(Protocol):
    def get_peak_assignments(self, day: date, *, time_slot: str = "") -> dict[str, Any]: ...


def staff_schedule_for_day(
    client: StaffScheduleClient,
    target_day: date,
    *,
    time_slot: str = "",
    include_owner: bool = False,
) -> dict[str, Any]:
    payload = client.get_peak_assignments(target_day, time_slot=time_slot)
    slots = _scheduled_slots(payload, include_owner=include_owner)
    rows = [row for slot_rows in slots.values() for row in slot_rows]
    unique_names = sorted({row["name"] for row in rows if row["name"]})
    return {
        "date": str(payload.get("date") or target_day.isoformat()),
        "time_slot": time_slot,
        "include_owner": include_owner,
        "summary": {
            "slots": len(slots),
            "scheduled": len(rows),
            "unique_instructors": len(unique_names),
        },
        "slots": slots,
        "instructors": rows,
    }


def _scheduled_slots(payload: dict[str, Any], *, include_owner: bool) -> dict[str, list[dict[str, Any]]]:
    raw_slots = payload.get("slots") if isinstance(payload, dict) else {}
    if not isinstance(raw_slots, dict):
        return {}
    slots: dict[str, list[dict[str, Any]]] = {}
    for slot, body in raw_slots.items():
        rows = _slot_instructors(body, include_owner=include_owner)
        if rows:
            slots[str(slot)] = rows
    return slots


def _slot_instructors(body: Any, *, include_owner: bool) -> list[dict[str, Any]]:
    raw_rows = []
    if isinstance(body, dict):
        raw_rows.extend(_dict_rows(body.get("waitingInstructors")))
        for class_row in _dict_rows(body.get("classes")):
            raw_rows.extend(_dict_rows(class_row.get("instructors")))
            instructor = class_row.get("instructor")
            if isinstance(instructor, dict):
                raw_rows.append(instructor)
    elif isinstance(body, list):
        raw_rows.extend(_dict_rows(body))

    rows = [_scheduled_row(row) for row in raw_rows]
    rows = [row for row in rows if row["name"]]
    if not include_owner:
        rows = [row for row in rows if not row["is_owner"]]
    return _dedupe_rows(rows)


def _scheduled_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "instructor_id": _to_int(row.get("id") or row.get("instructor_id")),
        "name": str(row.get("name") or row.get("instructor_name") or ""),
        "is_owner": bool(row.get("isOwner") or row.get("is_owner")),
    }


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)] if isinstance(value, list) else []


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for row in rows:
        key = (row["instructor_id"], row["name"])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
