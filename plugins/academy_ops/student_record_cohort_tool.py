"""Read-only latest record aggregation for current PACA students."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

from .academy_api import AcademyApiError
from .academy_query_tools import _int_arg, _json_error, _json_ok, _resolve_client
from .response_guidance import academy_response_guidance
from .student_records_tool import _event_matches, _float_or_none, _record_day


DEFAULT_LIMIT = 80
MAX_LIMIT = 200
MAX_WORKERS = 8


def register_student_record_cohort_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_student_record_cohort_latest",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "event_query": {"type": "string", "description": "조회할 실기 종목명."},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": DEFAULT_LIMIT},
            },
            "required": ["event_query"],
            "additionalProperties": False,
        },
        handler=_student_record_cohort_tool_handler,
        description=(
            "PACA 재원생 기준으로 Peak 최신 실기 기록을 종목별로 집계한다. "
            "Use for current enrolled students / 재원생 기준 latest records, gender-separated averages, "
            "rankings, and name lists. This is NOT 월말테스트 참가자 집계; use monthly_test only when "
            "the user explicitly asks 월말테스트/정기평가/test participants."
        ),
    )


def _student_record_cohort_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    event_query = str(payload.get("event_query") or "").strip()
    if not event_query:
        return _json_error("조회할 기록 종목을 알려줘.")
    limit = _int_arg(payload.get("limit"), default=DEFAULT_LIMIT, maximum=MAX_LIMIT)
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        profiles = _active_profile_map(client_or_error)
        students = _current_peak_students(client_or_error.list_peak_students(), profiles)
        rows = _latest_records_for_students(client_or_error, students, profiles, event_query)
    except (AcademyApiError, ValueError) as exc:
        return _json_error(str(exc))
    groups = _group_rows(rows, limit=limit)
    summary = _summary(students, rows, groups)
    event_name = _event_name(rows, event_query)
    return _json_ok(
        {
            "operation": "student.record_cohort_latest",
            "basis": "paca_active_students_latest_peak_record",
            "event": {"query": event_query, "name": event_name},
            "summary": summary,
            "groups": groups,
            "message": _message(event_name, summary, groups),
            "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
        }
    )


def _active_profile_map(client: Any) -> dict[int, dict[str, Any]]:
    try:
        rows = client.list_paca_students(status="active")
    except (AcademyApiError, AttributeError):
        rows = _search_active_paca_students(client)
    profiles: dict[int, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict):
            paca_id = _to_int(row.get("id") or row.get("student_id"))
            if paca_id and _is_current_student(row):
                profiles[paca_id] = row
    return profiles


def _current_peak_students(rows: list[dict[str, Any]], profiles: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    students: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        paca_id = _to_int(row.get("paca_student_id"))
        if paca_id in profiles:
            students.append(row)
    return students


def _latest_records_for_students(
    client: Any,
    students: list[dict[str, Any]],
    profiles: dict[int, dict[str, Any]],
    event_query: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(students)))) as pool:
        futures = {pool.submit(_student_latest_record, client, student, profiles, event_query): student for student in students}
        for future in as_completed(futures):
            record = future.result()
            if record is not None:
                rows.append(record)
    rows.sort(key=lambda item: _sort_value(item), reverse=True)
    return rows


def _student_latest_record(
    client: Any,
    student: dict[str, Any],
    profiles: dict[int, dict[str, Any]],
    event_query: str,
) -> dict[str, Any] | None:
    peak_id = _to_int(student.get("id"))
    if not peak_id:
        return None
    matching: list[dict[str, Any]] = []
    for record in client.list_peak_records(peak_id):
        if not isinstance(record, dict):
            continue
        event_name = str(record.get("record_type_name") or "")
        if not _event_matches(event_query, event_name):
            continue
        value = _float_or_none(record.get("value"))
        if value is None:
            continue
        matching.append(record)
    if not matching:
        return None
    latest = max(matching, key=lambda item: _record_day(item.get("measured_at")) or date.min)
    paca_id = _to_int(student.get("paca_student_id"))
    profile = profiles.get(paca_id, {})
    value = _float_or_none(latest.get("value"))
    if value is None:
        return None
    return {
        "name": _name(student, profile),
        "meta": _meta(student, profile),
        "gender": _gender(student, profile),
        "event_name": str(latest.get("record_type_name") or ""),
        "measured_at": str(latest.get("measured_at") or ""),
        "value": value,
        "unit": str(latest.get("unit") or ""),
        "direction": str(latest.get("direction") or ""),
    }


def _group_rows(rows: list[dict[str, Any]], *, limit: int) -> dict[str, dict[str, Any]]:
    groups = {
        "male": {"label": "남학생", "avg_label": "남자 평균", "rows": []},
        "female": {"label": "여학생", "avg_label": "여자 평균", "rows": []},
        "unknown": {"label": "성별 미기록", "avg_label": "미기록 평균", "rows": []},
    }
    for row in rows:
        key = row["gender"] if row["gender"] in groups else "unknown"
        groups[key]["rows"].append(row)
    for group in groups.values():
        group["rows"] = group["rows"][:limit]
        group["average"] = _average(group["rows"])
    return groups


def _summary(
    students: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    groups: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "current_students": len(students),
        "students_with_records": len(rows),
        "male_count": len(groups["male"]["rows"]),
        "female_count": len(groups["female"]["rows"]),
        "unknown_gender_count": len(groups["unknown"]["rows"]),
        "male_average": groups["male"]["average"],
        "female_average": groups["female"]["average"],
        "unknown_gender_average": groups["unknown"]["average"],
    }


def _message(event_name: str, summary: dict[str, Any], groups: dict[str, dict[str, Any]]) -> str:
    lines = [
        f"현재 재원생 기준 최신 {event_name} 기록",
        f"- 남자 평균: {_format_value(summary['male_average'], _unit(groups['male']['rows']))} ({summary['male_count']}명)",
        f"- 여자 평균: {_format_value(summary['female_average'], _unit(groups['female']['rows']))} ({summary['female_count']}명)",
    ]
    for key in ("male", "female"):
        rows = groups[key]["rows"]
        if not rows:
            continue
        label = groups[key]["label"]
        names = ", ".join(f"{row['name']} {_format_value(row['value'], row['unit'])}" for row in rows[:12])
        lines.append(f"- {label} 명단: {names}")
    if summary["unknown_gender_count"]:
        lines.append(f"- 성별 미기록: {summary['unknown_gender_count']}명")
    return "\n".join(lines)


def _search_active_paca_students(client: Any) -> list[dict[str, Any]]:
    try:
        rows = client.search_paca_students("")
    except (AcademyApiError, AttributeError):
        return []
    return [row for row in rows if isinstance(row, dict) and _is_current_student(row)]


def _is_current_student(row: dict[str, Any]) -> bool:
    return _norm(row.get("status") or row.get("student_status")) == "active"


def _gender(row: dict[str, Any], profile: dict[str, Any]) -> str:
    value = _norm(row.get("gender") or profile.get("gender") or profile.get("sex"))
    if value in {"male", "m", "남", "남자", "남학생"}:
        return "male"
    if value in {"female", "f", "여", "여자", "여학생"}:
        return "female"
    return "unknown"


def _name(row: dict[str, Any], profile: dict[str, Any]) -> str:
    return str(row.get("name") or row.get("student_name") or profile.get("name") or "학생")


def _meta(row: dict[str, Any], profile: dict[str, Any]) -> str:
    parts = [str(profile.get(key) or row.get(key) or "").strip() for key in ("school", "grade")]
    return " ".join(part for part in parts if part)


def _average(rows: list[dict[str, Any]]) -> float | None:
    values = [float(row["value"]) for row in rows if row.get("value") is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _event_name(rows: list[dict[str, Any]], fallback: str) -> str:
    return str(rows[0].get("event_name") or fallback) if rows else fallback


def _unit(rows: list[dict[str, Any]]) -> str:
    return str(rows[0].get("unit") or "") if rows else ""


def _format_value(value: Any, unit: str) -> str:
    if value is None:
        return "기록 없음"
    number = float(value)
    label = str(int(number)) if number.is_integer() else f"{number:.1f}"
    return f"{label}{unit}"


def _sort_value(row: dict[str, Any]) -> float:
    value = float(row.get("value") or 0)
    direction = _norm(row.get("direction"))
    return -value if direction in {"lower", "low", "asc", "낮을수록"} else value


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()
