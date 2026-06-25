"""Display helpers for practical recommendation events."""

from __future__ import annotations

from typing import Any


def recommendation_event_info(payload: Any) -> dict[str, Any]:
    """Normalize practical events for recommendation display."""
    events = _event_names(_payload_value(payload, "events"))
    stage1_events = _event_names(_payload_value(payload, "stage1_events"))
    selection_rule = str(_payload_value(payload, "selection_rule") or "")
    has_analysis_stage = _has_analysis_text(selection_rule, events)
    if stage1_events and has_analysis_stage:
        stage1_text = ", ".join(stage1_events[:4])
        return {
            "events": stage1_events[:6],
            "display_events": [
                f"1단계: {stage1_text}",
                "2단계: 스포츠분야 분석·질의응답",
            ],
            "event_note": "1단계 실기 100% 선발 후 2단계 스포츠분야 분석·질의응답 평가",
        }
    return {
        "events": events[:6],
        "display_events": events[:6],
        "event_note": None,
    }


def _payload_value(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _event_names(value: Any) -> list[str]:
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    names: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = item.get("name") or item.get("event") or item.get("title")
        else:
            text = item
        clean = str(text or "").strip()
        if clean:
            names.append(clean)
    return names


def _has_analysis_text(selection_rule: str, events: list[str]) -> bool:
    text = " ".join([selection_rule, *events])
    return "스포츠분야" in text and "질의응답" in text
