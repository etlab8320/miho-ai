"""Max academy motion-analysis variables API client."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from miho_constants import get_miho_home

API_KEY_ENV = "MAX_ANALYSIS_VARIABLES_API_KEY"
BASE_URL = "https://umfit-api.onrender.com/api/gait-analysis/external/v1/max"
VARIABLES_ENDPOINT = f"{BASE_URL}/analysis-variables"
DEFAULT_LIMIT = 1000
MAX_LIMIT = 1000
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_PAGES = 20
MAX_PAGES = 200
QUERY_FIELDS = ("academy_id", "academy_name", "sport", "from_date", "to_date")
CLIENT_FILTER_FIELDS = ("student_name", "student_query")
SPORT_ALIASES = {
    "slj": "slj",
    "standinglongjump": "slj",
    "longjump": "slj",
    "제멀": "slj",
    "제자리멀리뛰기": "slj",
    "제자리멀리": "slj",
    "sprint": "sprint",
    "스프린트": "sprint",
    "달리기": "sprint",
}


def max_analysis_variables_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = build_max_analysis_variables_response(args or {})
    return json.dumps(payload, ensure_ascii=False)


def build_max_analysis_variables_response(args: dict[str, Any]) -> dict[str, Any]:
    api_key = _resolve_api_key()
    if not api_key:
        return _error(
            "missing_api_key",
            f"{API_KEY_ENV}가 설정되어 있지 않아 맥스 분석 변인 데이터를 조회할 수 없다.",
        )

    limit = _bounded_int(args.get("limit"), default=DEFAULT_LIMIT, minimum=1, maximum=MAX_LIMIT)
    offset = _bounded_int(args.get("offset"), default=0, minimum=0, maximum=10_000_000)
    timeout = _bounded_int(args.get("timeout_seconds"), default=DEFAULT_TIMEOUT_SECONDS, minimum=3, maximum=120)
    client_filters = _client_filters(args)
    collect_all = bool(args.get("collect_all_pages")) or bool(client_filters)
    max_pages = _bounded_int(args.get("max_pages"), default=DEFAULT_MAX_PAGES, minimum=1, maximum=MAX_PAGES)
    params = _query_params(args, limit=limit, offset=offset)

    if collect_all:
        return _collect_pages(
            params=params,
            api_key=api_key,
            timeout=timeout,
            limit=limit,
            max_pages=max_pages,
            client_filters=client_filters,
        )
    page = _fetch_page(params=params, api_key=api_key, timeout=timeout)
    if not page["ok"]:
        return page
    return _success_response(
        records=page["records"],
        query=params,
        pages_fetched=1,
        next_offset=offset + limit if len(page["records"]) >= limit else None,
        exhausted=len(page["records"]) < limit,
        collect_all_pages=False,
        warnings=[],
        client_filters=client_filters,
    )


def _collect_pages(
    *,
    params: dict[str, Any],
    api_key: str,
    timeout: int,
    limit: int,
    max_pages: int,
    client_filters: dict[str, str],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    current_offset = _safe_int(params.get("offset"), 0)
    pages_fetched = 0
    exhausted = False
    for _ in range(max_pages):
        page_params = {**params, "offset": current_offset}
        page = _fetch_page(params=page_params, api_key=api_key, timeout=timeout)
        if not page["ok"]:
            return {**page, "partial_records": records, "pages_fetched": pages_fetched}
        page_records = page["records"]
        records.extend(page_records)
        pages_fetched += 1
        if len(page_records) < limit:
            exhausted = True
            break
        current_offset += limit
    if not exhausted:
        warnings.append("최대 페이지 수까지 조회했다. 더 필요한 경우 max_pages를 늘려 이어서 조회해야 한다.")
    return _success_response(
        records=records,
        query={**params, "offset": _safe_int(params.get("offset"), 0)},
        pages_fetched=pages_fetched,
        next_offset=None if exhausted else current_offset,
        exhausted=exhausted,
        collect_all_pages=True,
        warnings=warnings,
        client_filters=client_filters,
    )


def _fetch_page(*, params: dict[str, Any], api_key: str, timeout: int) -> dict[str, Any]:
    try:
        payload = _http_get_json(VARIABLES_ENDPOINT, params=params, api_key=api_key, timeout=timeout)
    except urllib.error.HTTPError as exc:
        return _error(_http_error_code(exc), _http_error_message(exc), query=params)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return _error("network_error", _network_error_message(exc), query=params)
    except (json.JSONDecodeError, ValueError) as exc:
        return _error("invalid_response", _invalid_response_message(exc), query=params)
    return {"ok": True, "records": _extract_records(payload)}


def _http_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> Any:
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value not in ("", None)})
    url = f"{endpoint}?{query}" if query else endpoint
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "miho-agent sports_performance",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - documented external API.
        return json.loads(response.read().decode("utf-8"))


def _success_response(
    *,
    records: list[dict[str, Any]],
    query: dict[str, Any],
    pages_fetched: int,
    next_offset: int | None,
    exhausted: bool,
    collect_all_pages: bool,
    warnings: list[str],
    client_filters: dict[str, str],
) -> dict[str, Any]:
    original_count = len(records)
    filtered_records = _apply_client_filters(records, client_filters)
    if client_filters and original_count and not filtered_records:
        warnings = [
            *warnings,
            "학생명 조건과 일치하는 운동분석 API 기록을 찾지 못했다. 이름, 지점, 기간 조건을 확인해야 한다.",
        ]
    display_query = {**query, **client_filters}
    latest_record = _latest_record(filtered_records)
    session_summaries = _session_summaries(filtered_records)
    return {
        "ok": True,
        "source": "max_analysis_variables_api",
        "endpoint": VARIABLES_ENDPOINT,
        "auth": {"env_var": API_KEY_ENV, "configured": True},
        "scope": _scope(display_query),
        "query": display_query,
        "pagination": {
            "limit": query.get("limit"),
            "offset": query.get("offset"),
            "collect_all_pages": collect_all_pages,
            "pages_fetched": pages_fetched,
            "next_offset": next_offset,
            "exhausted": exhausted,
        },
        "record_count": len(filtered_records),
        "latest_record": latest_record,
        "llm_context": _llm_context(latest_record, session_summaries),
        "session_summaries": session_summaries,
        "records": filtered_records,
        "summary": _summary(filtered_records),
        "variables": _variables(filtered_records),
        "student_filter": _student_filter_summary(client_filters, original_count, len(filtered_records)),
        "warnings": warnings,
        "reviewer": _api_reviewer(filtered_records, display_query, warnings),
    }


def _query_params(args: dict[str, Any], *, limit: int, offset: int) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    for field in QUERY_FIELDS:
        value = str(args.get(field) or "").strip()
        if value:
            params[field] = _normalize_sport(value) if field == "sport" else value
    return params


def _normalize_sport(value: str) -> str:
    compact = _compact(value).lower()
    return SPORT_ALIASES.get(compact, value.strip().lower())


def _client_filters(args: dict[str, Any]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for field in CLIENT_FILTER_FIELDS:
        value = str(args.get(field) or "").strip()
        if not value:
            continue
        filters["student_name"] = value
        break
    return filters


def _apply_client_filters(records: list[dict[str, Any]], filters: dict[str, str]) -> list[dict[str, Any]]:
    student_query = filters.get("student_name", "")
    if not student_query:
        return records
    return [row for row in records if _student_name_matches(student_query, _text(row.get("student_name")))]


def _student_name_matches(query: str, candidate: str) -> bool:
    needle = _compact(query)
    haystack = _compact(candidate)
    return bool(needle and haystack and (needle in haystack or haystack in needle))


def _student_filter_summary(filters: dict[str, str], original_count: int, filtered_count: int) -> dict[str, Any]:
    if not filters:
        return {"active": False, "matched": True, "original_record_count": original_count}
    return {
        "active": True,
        "student_name": filters["student_name"],
        "matched": filtered_count > 0,
        "original_record_count": original_count,
        "filtered_record_count": filtered_count,
    }


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if "student_name" in payload or "variable_key" in payload:
            return [payload]
    raise ValueError("맥스 분석 API 응답 구조를 해석할 수 없다.")


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    measured = sorted(_text(row.get("measured_at")) for row in records if _text(row.get("measured_at")))
    return {
        "student_names": _unique(records, "student_name"),
        "academy_count": len(_unique(records, "academy_id")),
        "academy_names": _unique(records, "academy_name"),
        "sports": _unique(records, "sport"),
        "session_count": len(_unique(records, "session_id")),
        "variable_key_count": len(_unique(records, "variable_key")),
        "measured_from": measured[0] if measured else "",
        "measured_to": measured[-1] if measured else "",
    }


def _variables(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    variables: list[dict[str, str]] = []
    for row in records:
        key = _text(row.get("variable_key"))
        name = _text(row.get("variable_name"))
        if not key and not name:
            continue
        item = {
            "variable_key": key,
            "variable_name": name,
            "unit": _text(row.get("unit")),
            "sport": _text(row.get("sport")),
            "phase": _text(row.get("phase")),
        }
        marker = tuple(item.values())
        if marker in seen:
            continue
        seen.add(marker)
        variables.append(item)
    return sorted(variables, key=lambda item: (item["sport"], item["phase"], item["variable_key"], item["variable_name"]))


def _latest_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {}
    row = sorted(records, key=lambda item: (_text(item.get("measured_at")), _text(item.get("session_id"))))[-1]
    return {
        "student_name": _text(row.get("student_name")),
        "academy_name": _text(row.get("academy_name")),
        "sport": _text(row.get("sport")),
        "measured_at": _text(row.get("measured_at")),
        "record_value": row.get("record_value"),
        "record_unit": _text(row.get("record_unit")),
        "session_id": _text(row.get("session_id")),
    }


def _session_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        key = _text(row.get("session_id")) or f"{_text(row.get('student_name'))}:{_text(row.get('measured_at'))}"
        grouped.setdefault(key, []).append(row)

    summaries: list[dict[str, Any]] = []
    for session_id, rows in grouped.items():
        head = sorted(rows, key=lambda item: _text(item.get("measured_at")))[-1]
        summaries.append(
            {
                "session_id": session_id,
                "student_name": _text(head.get("student_name")),
                "academy_name": _text(head.get("academy_name")),
                "sport": _text(head.get("sport")),
                "measured_at": _text(head.get("measured_at")),
                "record_value": head.get("record_value"),
                "record_unit": _text(head.get("record_unit")),
                "variable_count": len(rows),
                "variables": _compact_variables(rows),
            }
        )
    return sorted(summaries, key=lambda item: (item["measured_at"], item["session_id"]), reverse=True)


def _compact_variables(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variables: list[dict[str, Any]] = []
    for row in rows:
        variables.append(
            {
                "variable_key": _text(row.get("variable_key")),
                "variable_name": _text(row.get("variable_name")),
                "value": row.get("variable_value"),
                "unit": _text(row.get("unit")),
                "phase": _text(row.get("phase")),
            }
        )
    return sorted(variables, key=lambda item: (item["phase"], item["variable_key"], item["variable_name"]))


def _llm_context(
    latest_record: dict[str, Any],
    session_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    latest = _record_label(latest_record)
    previous = _record_label(session_summaries[1]) if len(session_summaries) > 1 else ""
    variables = session_summaries[0]["variables"] if session_summaries else []
    return {
        "compact_summary_ko": f"최신 제멀 기록: {latest}. 이전 기록: {previous or '없음'}.",
        "latest_record": latest,
        "previous_record": previous,
        "latest_jump_distance_cm": latest_record.get("record_value"),
        "previous_jump_distance_cm": session_summaries[1].get("record_value") if len(session_summaries) > 1 else None,
        "top_variable_samples": variables[:5],
        "latest_session_variable_count": session_summaries[0]["variable_count"] if session_summaries else 0,
        "latest_session_variables": variables,
        "guidance_ko": (
            "최종 답변에서는 records 전체보다 latest_record, session_summaries, "
            "llm_context를 우선 근거로 사용한다."
        ),
    }


def _record_label(record: dict[str, Any]) -> str:
    if not record:
        return ""
    measured_at = _text(record.get("measured_at"))
    value = record.get("record_value")
    unit = _text(record.get("record_unit"))
    if value in ("", None):
        return measured_at
    return f"{measured_at} / {value}{unit}".strip()


def _api_reviewer(
    records: list[dict[str, Any]],
    query: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    status = "pass"
    reviewer_warnings = list(warnings)
    if query.get("student_name") and not records:
        status = "retry_needed"
        reviewer_warnings.append("학생명 조건에 맞는 MAX 운동분석 API 기록이 없다.")
    return {
        "name": "sports_max_api_reviewer",
        "status": status,
        "mode": "deterministic_api_integrity_gate",
        "checked": ["API 원천", "학생/종목/지표", "페이지/필터"],
        "warnings": reviewer_warnings,
        "retry_tools": ["sports_max_analysis_variables"] if status == "retry_needed" else [],
        "retry_instruction_ko": (
            "학생명, 지점, 기간, 종목 조건을 조정해 MAX 운동분석 API를 다시 조회해 주세요."
            if status == "retry_needed"
            else ""
        ),
    }


def _scope(query: dict[str, Any]) -> str:
    if query.get("academy_id") or query.get("academy_name"):
        return "specific_academy"
    return "all_academies"


def _unique(records: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({_text(row.get(key)) for row in records if _text(row.get(key))})


def _resolve_api_key() -> str:
    value = os.getenv(API_KEY_ENV, "").strip()
    if value:
        return value
    try:
        from miho_cli.env_loader import load_miho_dotenv

        load_miho_dotenv(miho_home=get_miho_home())
    except Exception:
        return ""
    return os.getenv(API_KEY_ENV, "").strip()


def _error(code: str, message: str, *, query: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "ok": False,
        "source": "max_analysis_variables_api",
        "endpoint": VARIABLES_ENDPOINT,
        "error_code": code,
        "errors": [message],
        "auth": {"env_var": API_KEY_ENV, "configured": code != "missing_api_key"},
    }
    if query is not None:
        payload["query"] = query
    return payload


def _http_error_code(exc: urllib.error.HTTPError) -> str:
    if exc.code in {401, 403}:
        return "auth_failed"
    if exc.code == 429:
        return "rate_limited"
    if 400 <= exc.code < 500:
        return "bad_request"
    return "server_error"


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    if exc.code in {401, 403}:
        return f"API 인증에 실패했다. {API_KEY_ENV} 값을 확인하거나 새 키로 교체해야 한다."
    if exc.code == 429:
        return "외부 분석 API 요청이 너무 많다. 잠시 뒤 다시 조회해야 한다."
    if 400 <= exc.code < 500:
        return "조회 조건이 올바르지 않다. 교육원, 종목, 날짜, 페이지 조건을 다시 확인해야 한다."
    return "외부 분석 API 서버가 일시적으로 응답하지 않는다. 잠시 뒤 다시 조회해야 한다."


def _network_error_message(exc: BaseException) -> str:
    del exc
    return "외부 분석 API에 연결하지 못했다. 네트워크 상태나 API 서버 상태를 확인해야 한다."


def _invalid_response_message(exc: BaseException) -> str:
    del exc
    return "외부 분석 API 응답 형식이 예상과 달라 결과를 확정할 수 없다."


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _compact(value: str) -> str:
    return "".join(str(value or "").lower().split())
