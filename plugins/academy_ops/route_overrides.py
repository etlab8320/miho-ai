"""Output-contract corrections for academy natural routes.

Uses embedding-based semantic detection of the requested output format
(image / card) via :mod:`plugins.academy_ops.semantic_intents`. When the
embedding provider is unavailable, routing is disabled, or the match is
ambiguous, semantic_intents returns None and no override is applied.
"""

from __future__ import annotations

from typing import Any

from . import semantic_intents

OUTPUT_INTENT_GROUP = "academy_output_format"
OUTPUT_INTENTS: dict[str, tuple[str, ...]] = {
    "image": (
        "이미지로 보여줘",
        "사진으로 줘",
        "png 파일로 만들어줘",
        "달력 이미지로 그려줘",
        "캘린더로 보여줘",
        "그림으로 보여줘",
    ),
    "card": (
        "학생 관리카드로 만들어줘",
        "학생 카드로 보여줘",
        "관리카드 뽑아줘",
        "학생관리 카드로 정리해줘",
    ),
    "none": (
        "그냥 텍스트로 알려줘",
        "출결 내역 말로 설명해줘",
        "수치만 알려줘",
        "요약해서 말해줘",
    ),
}

_last_output: dict[str, Any] = {"text": None, "label": None, "hit": False}


def _semantic_output(text: str) -> str | None:
    """Semantic output-format intent for *text*, with a 1-entry cache.

    ``forced_tool_for_output_request`` and ``should_render_attendance_day_image``
    are both called on the same cleaned message; caching avoids a second
    embedding round-trip.
    """
    key = text or ""
    if _last_output["hit"] and _last_output["text"] == key:
        return _last_output["label"]
    label = semantic_intents.classify(
        key, OUTPUT_INTENT_GROUP, OUTPUT_INTENTS, negative_label="none", min_margin=0.04
    )
    _last_output["text"] = key
    _last_output["label"] = label
    _last_output["hit"] = True
    return label


def forced_tool_for_output_request(text: str, tool_name: str) -> str:
    label = _semantic_output(text)
    if label is None:
        return ""
    if tool_name == "academy_student_attendance_range" and label == "image":
        return "academy_student_attendance_calendar_image"
    if tool_name == "academy_student_summary" and label in ("card", "image"):
        return "academy_student_card_image"
    if tool_name == "academy_student_record_lookup" and label == "image":
        return "academy_student_record_chart_image"
    return ""


def should_render_attendance_day_image(text: str, tool_name: str) -> bool:
    label = _semantic_output(text)
    if label is None:
        return False
    return tool_name == "academy_attendance_day" and label == "image"
