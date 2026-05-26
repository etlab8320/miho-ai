"""Tool handler for read-only Peak instructor schedule lookup."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from .academy_api import AcademyApiError
from .academy_query_tools import _resolve_client
from .response_guidance import academy_response_guidance
from .staff_schedule import staff_schedule_for_day


def _staff_schedule_day_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    target_day = _date_arg(payload.get("date"))
    if target_day is None:
        return _json_error("조회 날짜를 YYYY-MM-DD로 지정해줘.")
    time_slot = str(payload.get("time_slot") or "").strip()
    include_owner = bool(payload.get("include_owner")) if isinstance(payload.get("include_owner"), bool) else False
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        schedule = staff_schedule_for_day(
            client_or_error,
            target_day,
            time_slot=time_slot,
            include_owner=include_owner,
        )
    except AcademyApiError as exc:
        return _json_error(str(exc))
    return _json_ok(
        {
            "operation": "staff.schedule_day",
            "date": schedule["date"],
            "time_slot": schedule["time_slot"],
            "include_owner": schedule["include_owner"],
            "summary": schedule["summary"],
            "slots": schedule["slots"],
            "instructors": schedule["instructors"],
            "message": _staff_schedule_message(schedule),
            "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
        }
    )


def _date_arg(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _staff_schedule_message(payload: dict[str, Any]) -> str:
    date_text = str(payload.get("date") or "")
    time_slot = str(payload.get("time_slot") or "")
    slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
    if not slots:
        return f"{date_text} 출근 예정 강사는 없어."
    if time_slot:
        names = _names(slots.get(time_slot, []))
        if not names:
            return f"{date_text} {_slot_label(time_slot)} 출근 예정 강사는 없어."
        return f"{date_text} {_slot_label(time_slot)} 출근 예정 강사: {', '.join(names)}."
    lines = [f"{date_text} 출근 예정 강사"]
    for slot, rows in slots.items():
        names = _names(rows)
        if names:
            lines.append(f"{_slot_label(str(slot))}: {', '.join(names)}")
    return "\n".join(lines)


def _names(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    return [str(row.get("name") or "") for row in rows if isinstance(row, dict) and row.get("name")]


def _slot_label(value: str) -> str:
    return {"morning": "오전반", "afternoon": "오후반", "evening": "저녁반"}.get(value, value or "시간대 미지정")


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


def _json_ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)
