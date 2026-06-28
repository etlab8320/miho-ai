"""National gender cohort model for sports motion reports."""

from __future__ import annotations

from math import ceil
from statistics import median
from typing import Any

from .variable_compare import comparison_pair, display_measure


def build_national_gender_model(
    *,
    student_payload: dict[str, Any],
    cohort_payload: dict[str, Any],
) -> dict[str, Any]:
    student_gender = _student_gender(student_payload)
    cohort_rows = _same_gender_rows(cohort_payload.get("records"), student_gender)
    sessions = _sessions(cohort_rows)
    top_sessions = _top_sessions(sessions, ratio=0.01)
    top_five_sessions = _top_sessions(sessions, ratio=0.05)
    top_ids = {session["id"] for session in top_sessions}
    top_five_ids = {session["id"] for session in top_five_sessions}
    top_rows = [row for row in cohort_rows if _session_id(row) in top_ids]
    top_five_rows = [row for row in cohort_rows if _session_id(row) in top_five_ids]
    values = _model_values(top_rows)
    return {
        "ok": bool(values),
        "basis": "national_gender_elite_1pct_from_max_api",
        "gender": student_gender or "all",
        "cohort_session_count": len(sessions),
        "elite_session_count": len(top_sessions),
        "elite_5pct_session_count": len(top_five_sessions),
        "variables": values,
        "variables_5pct": _model_values(top_five_rows),
        "comparison": _comparison_rows(student_gender, len(sessions), len(top_sessions), len(top_five_sessions)),
    }


def enrich_latest_variables_with_model(
    latest_variables: list[dict[str, Any]],
    *,
    model: dict[str, Any],
) -> list[dict[str, Any]]:
    model_values = model.get("variables") if isinstance(model.get("variables"), dict) else {}
    enriched: list[dict[str, Any]] = []
    for row in latest_variables:
        if not isinstance(row, dict):
            continue
        key = str(row.get("variable_key") or row.get("key") or "").strip()
        item = dict(row)
        model_item = model_values.get(key) if isinstance(model_values, dict) else None
        if isinstance(model_item, dict):
            value = _float(row.get("value", row.get("variable_value")))
            if value is not None:
                item["value"] = display_measure(key, value, row.get("unit"))
                item.pop("variable_value", None)
            item["elite_1pct"] = display_measure(key, model_item.get("value"), model_item.get("unit"))
            item["gap"] = _gap(key, row.get("value", row.get("variable_value")), model_item.get("value"), model_item.get("unit"))
            item["status"] = "상위 1% 모델"
        enriched.append(item)
    return enriched


def _student_gender(payload: dict[str, Any]) -> str:
    for row in payload.get("records") or []:
        if isinstance(row, dict):
            gender = str(row.get("gender") or row.get("student_gender") or row.get("sex") or "").strip()
            if gender:
                return gender
    return ""


def _same_gender_rows(raw_rows: Any, gender: str) -> list[dict[str, Any]]:
    rows = [row for row in raw_rows or [] if isinstance(row, dict)]
    if not gender:
        return rows
    return [row for row in rows if str(row.get("gender") or row.get("student_gender") or row.get("sex") or "").strip() == gender]


def _sessions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_session_id(row), []).append(row)
    sessions: list[dict[str, Any]] = []
    for session_id, session_rows in grouped.items():
        record = _record_value(session_rows)
        if record is None:
            continue
        sessions.append({"id": session_id, "record_value": record})
    return sessions


def _top_sessions(sessions: list[dict[str, Any]], *, ratio: float) -> list[dict[str, Any]]:
    if not sessions:
        return []
    top_count = max(1, ceil(len(sessions) * ratio))
    return sorted(sessions, key=lambda item: float(item["record_value"]), reverse=True)[:top_count]


def _model_values(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[float]] = {}
    units: dict[str, str] = {}
    for row in rows:
        key = str(row.get("variable_key") or "").strip()
        value = _float(row.get("variable_value", row.get("value")))
        if not key or value is None:
            continue
        grouped.setdefault(key, []).append(value)
        units.setdefault(key, str(row.get("unit") or "").strip())
    return {
        key: {"value": median(values), "unit": units.get(key, "")}
        for key, values in grouped.items()
        if values
    }


def _record_value(rows: list[dict[str, Any]]) -> float | None:
    for row in rows:
        value = _float(row.get("record_value"))
        if value is not None:
            return value
    return None


def _session_id(row: dict[str, Any]) -> str:
    explicit = str(row.get("session_id") or "").strip()
    if explicit:
        return explicit
    return ":".join(str(row.get(key) or "").strip() for key in ("student_name", "measured_at"))


def _comparison_rows(gender: str, session_count: int, top_count: int, top_five_count: int) -> list[dict[str, str]]:
    gender_label = gender or "전체 성별"
    return [
        {
            "label": "전국 성별 상위 1%",
            "value": f"{gender_label} {top_count}개 세션 모델",
            "note": f"MAX API 전체 {session_count}개 세션 중 기록 상위 1%",
        },
        {
            "label": "전국 성별 상위 5%",
            "value": f"{gender_label} {top_five_count}개 세션 모델",
            "note": f"MAX API 전체 {session_count}개 세션 중 기록 상위 5%",
        },
    ]


def _gap(key: str, current: Any, model: Any, unit: Any) -> str:
    current_value, model_value = comparison_pair(key, current, model)
    if current_value is None or model_value is None:
        return "계산 불가"
    diff = current_value - model_value
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.2f} {str(unit or '').strip()}".strip()


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
