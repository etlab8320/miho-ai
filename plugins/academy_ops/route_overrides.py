"""Output-contract corrections for academy natural routes."""

from __future__ import annotations


IMAGE_OUTPUT_MARKERS = ("이미지", "사진", "png", "달력", "캘린더")
CARD_OUTPUT_MARKERS = ("카드", "관리카드", "학생관리")


def forced_tool_for_output_request(text: str, tool_name: str) -> str:
    normalized = text.lower()
    if tool_name == "academy_student_attendance_range" and _has_any(normalized, IMAGE_OUTPUT_MARKERS):
        return "academy_student_attendance_calendar_image"
    if tool_name == "academy_student_summary" and _asks_for_card_image(normalized):
        return "academy_student_card_image"
    return ""


def should_render_attendance_day_image(text: str, tool_name: str) -> bool:
    return tool_name == "academy_attendance_day" and _has_any(text.lower(), IMAGE_OUTPUT_MARKERS)


def _asks_for_card_image(text: str) -> bool:
    return _has_any(text, CARD_OUTPUT_MARKERS) or _has_any(text, IMAGE_OUTPUT_MARKERS)


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)
