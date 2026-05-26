"""Formatting helpers for academy consultation candidate results."""

from __future__ import annotations

from typing import Any


def consultation_candidates_message(candidates: list[dict[str, Any]], period_days: int) -> str:
    safe_candidates = [item for item in candidates if isinstance(item, dict)]
    if not safe_candidates:
        return f"최근 {period_days}일 기준 상담 우선 후보는 없어."
    lines = [f"상담 후보 {len(safe_candidates)}명"]
    for index, item in enumerate(safe_candidates[:10], start=1):
        student = item.get("student") if isinstance(item.get("student"), dict) else item
        name = str(student.get("name") or item.get("name") or "이름 없음")
        priority = _priority_label(item.get("priority"))
        score = _to_int(item.get("score"))
        reasons = [str(reason).strip() for reason in item.get("reasons") or [] if str(reason).strip()]
        record_text = _problem_record_text(item)
        if record_text:
            reasons.append(record_text)
        tags = [f"{index}. {name}"]
        if priority:
            tags.append(f"우선순위 {priority}")
        if score:
            tags.append(f"점수 {score}")
        reason_text = "; ".join(reasons[:4]) if reasons else "상담 사유 데이터 없음"
        lines.append(f"{' - '.join(tags)}: {reason_text}")
    return "\n".join(lines)


def _problem_record_text(item: dict[str, Any]) -> str:
    signals = item.get("signals") if isinstance(item.get("signals"), dict) else {}
    records = signals.get("records") if isinstance(signals.get("records"), dict) else {}
    problem_records = records.get("problem_records") if isinstance(records.get("problem_records"), list) else []
    names = [_record_label(row) for row in problem_records if isinstance(row, dict)]
    names = [name for name in names if name]
    return f"정체/하락 종목: {', '.join(names[:5])}" if names else ""


def _record_label(row: dict[str, Any]) -> str:
    name = str(row.get("event_name") or row.get("record_type_name") or "").strip()
    trend = {"declining": "하락", "plateau": "정체"}.get(str(row.get("trend") or "").strip().lower(), "")
    return f"{name}({trend})" if name and trend else name


def _priority_label(value: Any) -> str:
    text = str(value or "").strip()
    return {"high": "높음", "medium": "중간", "low": "낮음"}.get(text.lower(), text)


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
