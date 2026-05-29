"""Read-only Peak monthly assessment aggregate lookup."""

from __future__ import annotations

from datetime import date
from typing import Any

from . import semantic_intents
from .academy_api import AcademyApiError
from .academy_query_tools import _date_arg, _json_error, _json_ok, _resolve_client
from .response_guidance import academy_response_guidance
from .student_records_tool import _event_matches


def _monthly_test_records_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    event_query = str(payload.get("event_query") or "").strip()
    if not event_query:
        return _json_error("평균을 계산할 실기 종목을 알려줘.")
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        selected = _select_monthly_test(
            client_or_error.list_peak_monthly_tests(),
            test_id=_int_or_none(payload.get("test_id")),
            test_month=str(payload.get("test_month") or "").strip(),
            today=_date_arg(payload.get("today")) or date.today(),
        )
        if selected is None:
            return _json_error("조회할 월별 실기 평가를 찾지 못했어.")
        data = client_or_error.get_peak_monthly_test_records(int(selected.get("id") or 0))
    except (AcademyApiError, ValueError) as exc:
        return _json_error(str(exc))
    result = _aggregate(
        data,
        event_query=event_query,
        exclude_schools=_exclude_schools(payload.get("exclude_schools")),
        source_text=str(kwargs.get("source_text") or ""),
    )
    if result is None:
        return _json_error("해당 월별 실기 평가에서 요청한 종목 기록을 찾지 못했어.")
    result["assistant_guidance"] = academy_response_guidance(use_message_as_facts=True)
    return _json_ok(result)


def register_monthly_test_records_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_monthly_test_records",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "event_query": {"type": "string", "description": "평균을 계산할 실기 종목명 또는 약칭."},
                "test_id": {"type": "integer", "description": "특정 월별 실기 평가 ID."},
                "test_month": {"type": "string", "description": "조회 월. YYYY-MM 형식."},
                "exclude_schools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "평균에서 제외할 학교명 목록.",
                },
                "today": {"type": "string", "description": "기준일. YYYY-MM-DD 형식."},
            },
            "required": ["event_query"],
            "additionalProperties": False,
        },
        handler=_monthly_test_records_tool_handler,
        description=(
            "Return read-only aggregates from Peak monthly assessment participants. "
            "Use for recurring monthly practical assessment averages, rankings, participant-based event summaries, "
            "or school-excluded aggregate calculations. Do not use the ordinary latest student records endpoint "
            "for these participant-scoped assessment questions."
        ),
    )


def _select_monthly_test(
    tests: list[dict[str, Any]],
    *,
    test_id: int | None,
    test_month: str,
    today: date,
) -> dict[str, Any] | None:
    if test_id is not None:
        return next((item for item in tests if _int_or_none(item.get("id")) == test_id), None)
    month = test_month or today.strftime("%Y-%m")
    monthly_matches = [item for item in tests if str(item.get("test_month") or "") == month]
    if monthly_matches:
        active = [item for item in monthly_matches if str(item.get("status") or "") == "active"]
        return active[0] if active else monthly_matches[0]
    active = [item for item in tests if str(item.get("status") or "") == "active"]
    return active[0] if active else (tests[0] if tests else None)


def _aggregate(
    payload: dict[str, Any],
    *,
    event_query: str,
    exclude_schools: set[str],
    source_text: str = "",
) -> dict[str, Any] | None:
    event = _matching_event(payload.get("record_types"), event_query, fallback_text=source_text)
    if event is None:
        return None
    event_id = str(event.get("record_type_id") or event.get("id") or "")
    if not event_id:
        return None
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for participant in _list_dicts(payload.get("participants")):
        record = _participant_record(participant, event_id)
        if record is None or record <= 0:
            continue
        row = {
            "name": str(participant.get("name") or ""),
            "gender": str(participant.get("gender") or "").upper(),
            "school": str(participant.get("school") or ""),
            "value": record,
            "unit": str(event.get("unit") or ""),
        }
        if _normalize(row["school"]) in exclude_schools:
            excluded.append(row)
        else:
            included.append(row)
    return {
        "operation": "monthly_test.records",
        "test": payload.get("test") if isinstance(payload.get("test"), dict) else {},
        "event": {
            "id": int(event_id),
            "name": str(event.get("name") or ""),
            "unit": str(event.get("unit") or ""),
            "direction": str(event.get("direction") or ""),
        },
        "summary": _gender_summary(included),
        "excluded": {"count": len(excluded), "schools": sorted(exclude_schools), "records": excluded[:30]},
        "records": included[:80],
        "message": _message(payload, event, included, excluded),
    }


def _matching_event(value: Any, event_query: str, *, fallback_text: str = "") -> dict[str, Any] | None:
    items = _list_dicts(value)
    if not items:
        return None
    # 1) Semantic embedding match against the test's actual event names. Tries the
    #    LLM-extracted event_query first, then the raw user message, so a mis-extracted
    #    event_query (e.g. a test name landing in the event slot) is still recovered
    #    from the original phrasing. Unrelated text matches nothing above threshold,
    #    so it abstains rather than mismatching.
    names = [str(item.get("name") or "") for item in items]
    for query in (event_query, fallback_text):
        if not str(query or "").strip():
            continue
        index = semantic_intents.best_match_index(query, names)
        if index is not None:
            return items[index]
    # 2) Text fallback when no semantic provider is available (keeps prior behaviour).
    for item in items:
        candidate_names = [str(item.get("name") or ""), str(item.get("short_name") or "")]
        if any(_event_matches(event_query, name) for name in candidate_names):
            return item
    return None


def _participant_record(participant: dict[str, Any], event_id: str) -> float | None:
    records = participant.get("records")
    if not isinstance(records, dict):
        return None
    return _float_or_none(records.get(event_id))


def _gender_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    return {
        key: _summary([row["value"] for row in rows if row["gender"] == gender])
        for key, gender in (("male", "M"), ("female", "F"))
    }


def _summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "average": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": len(values),
        "average": round(sum(values) / len(values), 2),
        "min": min(values),
        "max": max(values),
    }


def _message(payload: dict[str, Any], event: dict[str, Any], included: list[dict[str, Any]], excluded: list[dict[str, Any]]) -> str:
    summary = _gender_summary(included)
    unit = str(event.get("unit") or "")
    test = payload.get("test") if isinstance(payload.get("test"), dict) else {}
    title = str(test.get("test_name") or "월별 실기 평가")
    male = summary["male"]
    female = summary["female"]
    return (
        f"{title} {event.get('name')} 평균은 "
        f"남학생 {male['average']:g}{unit}({male['count']}명), "
        f"여학생 {female['average']:g}{unit}({female['count']}명)이야. "
        f"제외 기록은 {len(excluded)}건이야."
    )


def _exclude_schools(value: Any) -> set[str]:
    if isinstance(value, str):
        return {_normalize(value)} if value.strip() else set()
    if isinstance(value, list):
        return {_normalize(item) for item in value if str(item or "").strip()}
    return set()


def _normalize(value: Any) -> str:
    return "".join(str(value or "").split()).lower()


def _list_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)] if isinstance(value, list) else []


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
