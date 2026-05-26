"""Read-only Peak daily plan lookup."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol


class PlanLookupClient(Protocol):
    def get_peak_plans(self, day: date, *, time_slot: str = "") -> dict[str, Any]: ...


def plan_lookup_for_day(
    client: PlanLookupClient,
    target_day: date,
    *,
    trainer_query: str = "",
    time_slot: str = "",
) -> dict[str, Any]:
    payload = client.get_peak_plans(target_day, time_slot=time_slot)
    plans = [_safe_plan(row) for row in _list_payload(payload, "plans")]
    if trainer_query:
        plans = [plan for plan in plans if trainer_query in plan["instructor_name"]]
    return {
        "date": str(payload.get("date") or target_day.isoformat()),
        "trainer_query": trainer_query,
        "time_slot": time_slot,
        "plans": plans,
        "summary": {
            "plans": len(plans),
            "exercises": sum(len(plan["exercises"]) for plan in plans),
            "completed": sum(plan["completed_count"] for plan in plans),
        },
    }


def _safe_plan(row: dict[str, Any]) -> dict[str, Any]:
    exercises = [_safe_exercise(item) for item in _list_value(row.get("exercises"))]
    completed_ids = {_id_text(item) for item in _list_value(row.get("completed_exercises"))}
    for exercise in exercises:
        exercise["completed"] = exercise["id"] in completed_ids
    return {
        "id": _to_int(row.get("id")),
        "date": str(row.get("date") or ""),
        "time_slot": str(row.get("time_slot") or ""),
        "instructor_id": _to_int(row.get("instructor_id")),
        "instructor_name": str(row.get("instructor_name") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "description": str(row.get("description") or ""),
        "exercises": exercises,
        "completed_count": sum(1 for exercise in exercises if exercise["completed"]),
    }


def _safe_exercise(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _id_text(item.get("exercise_id") or item.get("id")),
        "name": str(item.get("name") or "운동"),
        "note": str(item.get("note") or item.get("memo") or ""),
        "completed": False,
    }


def _list_payload(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key) if isinstance(payload, dict) else []
    return [item for item in _list_value(value) if isinstance(item, dict)]


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _id_text(value: Any) -> str:
    return str(value or "").strip()


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
