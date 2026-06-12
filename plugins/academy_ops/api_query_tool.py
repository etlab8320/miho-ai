"""Read-only generic PACA/Peak API query for requests no specialized tool covers."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Callable

from .academy_api import AcademyApiError
from .academy_query_tools import _json_error, _resolve_client

# Serialized results above this size get list-truncated so one broad query
# (e.g. 전체 재원생 명단) cannot blow up the conversation context.
MAX_RESULT_CHARS = 20_000


def _require_str(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        raise ValueError(f"'{key}' 인자가 필요해.")
    return value


def _opt_str(params: dict[str, Any], key: str, default: str = "") -> str:
    return str(params.get(key) or default).strip()


def _require_int(params: dict[str, Any], key: str) -> int:
    try:
        return int(params[key])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"'{key}' 인자(정수)가 필요해.") from None


def _require_date(params: dict[str, Any], key: str) -> date:
    raw = str(params.get(key) or "").strip()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"'{key}' 인자가 YYYY-MM-DD 형식이어야 해.") from None


_METHODS: dict[str, Callable[[Any, dict[str, Any]], Any]] = {
    "search_paca_students": lambda c, p: c.search_paca_students(_require_str(p, "query")),
    "list_paca_students": lambda c, p: c.list_paca_students(status=_opt_str(p, "status")),
    "get_paca_student_detail": lambda c, p: c.get_paca_student_detail(_require_int(p, "paca_student_id")),
    "list_paca_instructors": lambda c, p: c.list_paca_instructors(status=_opt_str(p, "status", "active")),
    "get_paca_instructor_attendance": lambda c, p: c.get_paca_instructor_attendance(
        _require_int(p, "instructor_id"), year=_require_int(p, "year"), month=_require_int(p, "month")
    ),
    "get_paca_academy_events": lambda c, p: c.get_paca_academy_events(
        _require_date(p, "start_date"), _require_date(p, "end_date")
    ),
    "list_paca_schedules": lambda c, p: c.list_paca_schedules(
        _require_date(p, "start_date"), _require_date(p, "end_date")
    ),
    "get_paca_schedule_attendance": lambda c, p: c.get_paca_schedule_attendance(_require_int(p, "schedule_id")),
    "get_paca_student_attendance": lambda c, p: c.get_paca_student_attendance(
        _require_int(p, "paca_student_id"), year_month=_require_str(p, "year_month")
    ),
    "list_paca_consultations": lambda c, p: c.list_paca_consultations(),
    "list_peak_monthly_tests": lambda c, p: c.list_peak_monthly_tests(),
    "get_peak_monthly_test_records": lambda c, p: c.get_peak_monthly_test_records(_require_int(p, "monthly_test_id")),
    "list_peak_students": lambda c, p: c.list_peak_students(),
    "get_peak_attendance": lambda c, p: c.get_peak_attendance(_require_date(p, "date")),
    "get_peak_assignments": lambda c, p: c.get_peak_assignments(
        _require_date(p, "date"), time_slot=_opt_str(p, "time_slot")
    ),
    "get_peak_plans": lambda c, p: c.get_peak_plans(_require_date(p, "date"), time_slot=_opt_str(p, "time_slot")),
    "list_peak_records": lambda c, p: c.list_peak_records(_require_int(p, "peak_student_id")),
}


def _fit_result(result: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "result": result}
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized) <= MAX_RESULT_CHARS or not isinstance(result, list):
        return payload
    total = len(result)
    kept = list(result)
    while kept and len(json.dumps({"ok": True, "result": kept}, ensure_ascii=False)) > MAX_RESULT_CHARS:
        kept = kept[: max(1, len(kept) // 2)]
    return {
        "ok": True,
        "result": kept,
        "truncated": True,
        "total_items": total,
        "shown_items": len(kept),
        "note": "결과가 커서 일부만 반환했어. params로 범위를 좁히거나 단계적으로 집계해.",
    }


def _api_query_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    method = str(payload.get("method") or "").strip()
    caller = _METHODS.get(method)
    if caller is None:
        return _json_error(f"지원하지 않는 method야: {method or '(빈 값)'}. 목록: {', '.join(sorted(_METHODS))}")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        result = caller(client_or_error, params)
    except ValueError as exc:
        return _json_error(str(exc))
    except AcademyApiError as exc:
        return _json_error(str(exc))
    return json.dumps(_fit_result(result), ensure_ascii=False)


def register_api_query_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_api_query",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": sorted(_METHODS),
                    "description": "호출할 읽기 전용 PACA/Peak API 메서드.",
                },
                "params": {
                    "type": "object",
                    "description": "메서드별 인자. 날짜는 YYYY-MM-DD, year_month는 YYYY-MM.",
                },
            },
            "required": ["method"],
            "additionalProperties": False,
        },
        handler=_api_query_tool_handler,
        description=(
            "Read-only generic PACA/Peak academy API query. Use ONLY when no specialized academy tool "
            "covers the request — e.g. 학원생 증감 추이, 등록/퇴원 통계, cross-cutting aggregation. "
            "Combine results across calls yourself (count, group by month, then render). Never writes data. "
            "Methods & params: search_paca_students(query) · list_paca_students(status?) — 재원생 명단 · "
            "get_paca_student_detail(paca_student_id) — 등록일 등 상세 · list_paca_instructors(status?) · "
            "get_paca_instructor_attendance(instructor_id, year, month) · "
            "get_paca_academy_events(start_date, end_date) · list_paca_schedules(start_date, end_date) · "
            "get_paca_schedule_attendance(schedule_id) · get_paca_student_attendance(paca_student_id, year_month) · "
            "list_paca_consultations() · list_peak_monthly_tests() · get_peak_monthly_test_records(monthly_test_id) · "
            "list_peak_students() · get_peak_attendance(date) · get_peak_assignments(date, time_slot?) · "
            "get_peak_plans(date, time_slot?) · list_peak_records(peak_student_id). "
            "Large list results are truncated with total_items/shown_items metadata — narrow params or aggregate stepwise."
        ),
    )
