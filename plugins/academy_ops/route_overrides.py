"""Output-contract corrections for academy natural routes.

Prefers embedding-based semantic detection of the requested output format
(image / card) via :mod:`plugins.academy_ops.semantic_intents`. Falls back to
the historical keyword logic only when no semantic embedding provider is
available, routing is disabled, or the match is ambiguous.
"""

from __future__ import annotations

from typing import Any

from . import semantic_intents

# EMERGENCY FALLBACK ONLY — keyword markers used solely when semantic_intents
# returns None (no embedding provider / routing disabled / ambiguous). The
# primary path is embedding similarity over OUTPUT_INTENTS below; these
# substrings must never be the primary classifier (see
# test_academy_no_hardcoded_nlp).
IMAGE_OUTPUT_MARKERS = ("이미지", "사진", "png", "달력", "캘린더")
CARD_OUTPUT_MARKERS = ("카드", "관리카드", "학생관리")

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
    explicit_image = _has_any(text.lower(), IMAGE_OUTPUT_MARKERS)
    if label is None:
        return _keyword_forced_tool(text, tool_name)
    if tool_name == "academy_student_attendance_range" and (label == "image" or explicit_image):
        return "academy_student_attendance_calendar_image"
    if tool_name == "academy_student_summary" and label in ("card", "image"):
        return "academy_student_card_image"
    if tool_name == "academy_student_record_lookup" and (label == "image" or explicit_image):
        return "academy_student_record_chart_image"
    return ""


def should_render_attendance_day_image(text: str, tool_name: str) -> bool:
    label = _semantic_output(text)
    if label is None:
        return _keyword_should_render(text, tool_name)
    return tool_name == "academy_attendance_day" and (label == "image" or _has_any(text.lower(), IMAGE_OUTPUT_MARKERS))


def _keyword_forced_tool(text: str, tool_name: str) -> str:
    normalized = text.lower()
    if tool_name == "academy_student_attendance_range" and _has_any(normalized, IMAGE_OUTPUT_MARKERS):
        return "academy_student_attendance_calendar_image"
    if tool_name == "academy_student_summary" and _asks_for_card_image(normalized):
        return "academy_student_card_image"
    if tool_name == "academy_student_record_lookup" and _has_any(normalized, IMAGE_OUTPUT_MARKERS):
        return "academy_student_record_chart_image"
    return ""


def _keyword_should_render(text: str, tool_name: str) -> bool:
    return tool_name == "academy_attendance_day" and _has_any(text.lower(), IMAGE_OUTPUT_MARKERS)


def _asks_for_card_image(text: str) -> bool:
    return _has_any(text, CARD_OUTPUT_MARKERS) or _has_any(text, IMAGE_OUTPUT_MARKERS)


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)
