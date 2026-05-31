"""Read-only Peak monthly assessment aggregate lookup."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from miho_constants import get_miho_home

from . import semantic_intents
from .academy_api import AcademyApiError
from .academy_query_tools import _date_arg, _json_error, _json_ok, _resolve_client
from .report_design import ColumnSpec, GroupSpec, ReportSpec, render_report_html
from .response_guidance import academy_response_guidance
from .student_card_capture import StudentCardCaptureError, capture_html_to_png
from .student_records_tool import _event_matches


def _monthly_test_records_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    event_query = str(payload.get("event_query") or "").strip()
    exclude_schools = _exclude_schools(payload.get("exclude_schools"))
    school_query = str(payload.get("school_query") or "").strip()
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

    # No specific event → full-events student table (image by default). This is
    # the "전체 종목 표로 이미지" path; never ask the user which event to pick.
    if not event_query:
        image_path = _all_events_table_image(
            data, exclude_schools=exclude_schools, school_query=school_query
        )
        if image_path is None:
            return _json_error("이 월별 실기 평가에서 참가자 기록을 찾지 못했어.")
        media = f"MEDIA:{image_path}"
        return _json_ok(
            {
                "operation": "monthly_test.all_events_image",
                "message": f"{_test_title(data)} 종목별 기록 표야. {media}",
                "media_tag": media,
                "image_path": str(image_path),
                # Hand the body agent the raw roster so a follow-up like
                # "그 학생만" / "특정 학생 기록만" can be answered by filtering
                # this data directly — no per-case tool/param needed.
                "test": data.get("test"),
                "record_types": data.get("record_types"),
                "participants": data.get("participants"),
                "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
            }
        )

    result = _aggregate(
        data,
        event_query=event_query,
        exclude_schools=exclude_schools,
        source_text=str(kwargs.get("source_text") or ""),
    )
    if result is None:
        return _json_error("해당 월별 실기 평가에서 요청한 종목 기록을 찾지 못했어.")
    result["assistant_guidance"] = academy_response_guidance(use_message_as_facts=True)
    return _json_ok(result)


def _test_title(payload: dict[str, Any]) -> str:
    test = payload.get("test") if isinstance(payload.get("test"), dict) else {}
    return str(test.get("test_name") or "월말 테스트")


def _direction_best(direction: str) -> str:
    """Map an event's scoring direction to the report column 'best' flag."""
    d = direction.lower()
    if any(k in d for k in ("asc", "down", "low", "less", "time", "초", "fast")):
        return "low"
    return "high"


def _gender_kr(value: Any) -> str:
    g = str(value or "").upper()
    return "남" if g == "M" else "여" if g == "F" else ""


def _all_events_table_image(
    payload: dict[str, Any],
    *,
    exclude_schools: set[str],
    school_query: str = "",
) -> str | None:
    """Render every event × every participant as one report image (gender-split)."""
    record_types = _list_dicts(payload.get("record_types"))
    participants = _list_dicts(payload.get("participants"))
    if not record_types or not participants:
        return None
    columns = [
        ColumnSpec(
            key=str(rt.get("record_type_id") or rt.get("id") or ""),
            label=str(rt.get("name") or ""),
            unit=str(rt.get("unit") or ""),
            best=_direction_best(str(rt.get("direction") or "")),
        )
        for rt in record_types
        if str(rt.get("record_type_id") or rt.get("id") or "")
    ]
    if not columns:
        return None

    school_norm = _normalize(school_query) if school_query else ""
    male: list[dict[str, Any]] = []
    female: list[dict[str, Any]] = []
    for participant in participants:
        school = str(participant.get("school") or "")
        norm = _normalize(school)
        if exclude_schools and norm in exclude_schools:
            continue
        if school_norm and norm != school_norm:
            continue
        row: dict[str, Any] = {
            "name": str(participant.get("name") or ""),
            "meta": " · ".join(p for p in (str(participant.get("school") or ""), _gender_kr(participant.get("gender"))) if p),
        }
        for col in columns:
            value = _participant_record(participant, col.key)
            if value is not None and value > 0:
                row[col.key] = value
        (male if _gender_kr(participant.get("gender")) == "남" else female).append(row)

    groups: list[GroupSpec] = []
    if male:
        groups.append(GroupSpec(label="남학생", kind="male", avg_label="남자 평균", rows=male))
    if female:
        groups.append(GroupSpec(label="여학생", kind="female", avg_label="여자 평균", rows=female))
    if not groups:
        return None

    test = payload.get("test") if isinstance(payload.get("test"), dict) else {}
    month = str(test.get("test_month") or "")
    title = f"{_test_title(payload)} 종목별 기록"
    subtitle_bits = [b for b in (month, f"참가 {len(male) + len(female)}명", "기준 Peak 월말테스트") if b]
    spec = ReportSpec(
        title=title,
        subtitle=" · ".join(subtitle_bits),
        columns=columns,
        groups=groups,
        rank_by=columns[0].key,
        note="기록 없는 학생은 평균에서 제외 · 성별 평균 분리",
    )
    html = render_report_html(spec)
    out_dir = get_miho_home() / "media_cache" / "academy_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex[:12]
    html_path = out_dir / f"{stem}.html"
    image_path = out_dir / f"{stem}.png"
    html_path.write_text(html, encoding="utf-8")
    rows_total = sum(len(g.rows) + 1 for g in groups) + len(groups)
    try:
        capture_html_to_png(html_path, image_path, width=1240, height=max(820, 430 + rows_total * 62))
    except StudentCardCaptureError:
        return None
    return str(image_path)


def register_monthly_test_records_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_monthly_test_records",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "event_query": {
                    "type": "string",
                    "description": "특정 종목의 평균만 원할 때 그 종목명/약칭. 전체 종목 표를 원하면 비워둔다.",
                },
                "school_query": {"type": "string", "description": "특정 학교 학생만 보고 싶을 때 정확한 학교명."},
                "test_id": {"type": "integer", "description": "특정 월별 실기 평가 ID."},
                "test_month": {"type": "string", "description": "조회 월. YYYY-MM 형식."},
                "exclude_schools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "제외할 학교명 목록.",
                },
                "today": {"type": "string", "description": "기준일. YYYY-MM-DD 형식."},
            },
            "additionalProperties": False,
        },
        handler=_monthly_test_records_tool_handler,
        description=(
            "Read-only Peak 월말테스트 records — the WHOLE cohort of participants in ONE monthly test "
            "(not a single student's history; for that use academy_student_record_lookup). "
            "Give event_query for a SINGLE event's gender-split average. "
            "LEAVE event_query EMPTY for a FULL all-events student table — when the user says "
            "'전체 종목/전부/다 / 참여학생 전부 / 표로 이미지로', this returns a rendered image (학생×종목 표 + 남녀 평균, trendy light design) AND the raw participant roster. "
            "For a follow-up like '그 학생만 / 특정 학생만' right after a 월말테스트, filter THAT returned roster — "
            "do not switch to academy_student_record_lookup (a different per-student endpoint). "
            "Never ask which event when the user wants all events. Use school_query to limit to one school."
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
