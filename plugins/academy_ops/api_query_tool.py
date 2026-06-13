"""Read-only generic PACA/Peak API query for requests no specialized tool covers."""

from __future__ import annotations

import json
import os
from pathlib import Path
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


# ── 학원 API 지도 — 전체 백엔드 카탈로그(화이트리스트 겸 사용 설명서) ──
# 미호가 수동 매핑 ~20개만 쓰던 것을 전 모듈로 확장 (scripts/build_academy_api_map.py).
# 정책(사장님 승인 2026-06-13): GET 전 모듈, 쓰기는 expenses(지출)만.
_API_MAP_PATH = Path(os.path.expanduser("~/.miho/academy_ops/academy_api_map.json"))
_API_MAP: dict | None = None


def _api_map() -> dict:
    global _API_MAP
    if _API_MAP is None:
        try:
            _API_MAP = json.loads(_API_MAP_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _API_MAP = {"modules": {}}
    return _API_MAP


def _map_search(query: str) -> dict[str, Any]:
    q = str(query or "").strip().lower()
    if not q:
        return {"ok": False, "error": "검색어(params.query)를 줘. 예: '지출', '급여', '결제', '상담'"}
    hits = []
    for name, mod in _api_map().get("modules", {}).items():
        mod_match = q in name.lower() or q in str(mod.get("desc", "")).lower() or q in mod.get("prefix", "")
        for e in mod.get("endpoints", []):
            if mod_match or q in e["path"].lower() or q in str(e.get("desc", "")).lower():
                hits.append({"module": name, "module_desc": mod.get("desc"), **e})
    return {
        "ok": True,
        "hits": hits[:30],
        "usage": "호출: method='call', params={'http_method': 'GET', 'path': '<위 path 그대로(:param은 실제 값으로)>', 'query': {...}, 'body': {...}}",
    } if hits else {
        "ok": True, "hits": [],
        "note": "지도에 없는 기능이야. 모듈 단위 키워드(학생/출결/결제/급여/지출/수입/상담/일정/리포트/성적/시즌/문자)로 다시 검색해봐.",
    }


def _match_template(http_method: str, path: str) -> dict | None:
    """실제 호출 path를 지도 템플릿(:param 세그먼트)과 대조 — 등재된 것만 통과."""
    segs = [s for s in path.split("?")[0].split("/") if s]
    for mod in _api_map().get("modules", {}).values():
        for e in mod.get("endpoints", []):
            if e["method"] != http_method.upper():
                continue
            t = [s for s in e["path"].split("/") if s]
            if len(t) == len(segs) and all(ts.startswith(":") or ts == ps for ts, ps in zip(t, segs)):
                return e
    return None


def _map_call(client: Any, params: dict[str, Any]) -> Any:
    http_method = str(params.get("http_method") or "GET").upper()
    path = str(params.get("path") or "").strip()
    if not path.startswith("/paca/"):
        raise ValueError("path는 /paca/ 로 시작해야 해 (지도의 path 그대로, :param은 실제 값으로 치환).")
    entry = _match_template(http_method, path)
    if entry is None:
        raise ValueError(
            f"{http_method} {path} 는 API 지도에 없어 호출할 수 없어. "
            "map_search로 등재된 경로를 먼저 확인해 (쓰기는 지출(expenses)만 허용)."
        )
    query = params.get("query") if isinstance(params.get("query"), dict) else None
    body = params.get("body") if isinstance(params.get("body"), dict) else None
    return client.request_path(http_method, path, params=query, json_body=body)


_METHODS["map_search"] = lambda c, p: _map_search(str(p.get("query") or ""))
_METHODS["call"] = _map_call


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
            "PACA/Peak 학원 API 범용 조회 — 전용 도구가 없는 학원 데이터 질문의 진입점. "
            "모르는 영역(지출/수입/결제/급여/리포트/시즌/문자 등 무엇이든)은 먼저 method='map_search', "
            "params={'query': '키워드'} 로 API 지도를 검색해라 — 전체 백엔드 24모듈 104개 엔드포인트의 "
            "기능 설명과 호출법이 나온다. 그 다음 method='call' 로 해당 path를 호출한다. "
            "쓰기는 지출(expenses)만 허용되고 나머지는 전부 읽기 전용이다. "
            "기존 고수준 메서드(search_paca_students 등)가 있는 작업은 그걸 우선 사용. "
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
