"""Attendance score helpers for official 수시 calculations."""

from __future__ import annotations

import re
from typing import Any

from .utils import _first_number


_ABSENCE_KEYS = (
    "unexcused_absence_days",
    "unexcused_absences",
    "unexcused_absence",
    "absence_days",
    "미인정결석",
    "무단결석",
)
_EVENT_KEYS = (
    "unexcused_late",
    "unexcused_late_days",
    "unexcused_early_leave",
    "unexcused_early_leave_days",
    "unexcused_result",
    "unexcused_result_days",
    "unexcused_late_early_leave_result",
    "미인정지각",
    "미인정조퇴",
    "미인정결과",
    "무단지각",
    "무단조퇴",
    "무단결과",
)


def score_attendance(attendance_logic: dict[str, Any], attendance: dict[str, Any]) -> dict[str, Any] | None:
    """Return a scored attendance component when a separate official table exists."""
    if not attendance_logic:
        return None
    status = str(attendance_logic.get("calculation_status") or "").lower()
    if "no_separate_attendance_component" in status:
        return None
    full_score = _first_number(attendance_logic.get("full_score"))
    if full_score is None or full_score <= 0:
        return None
    absence_days = _attendance_absence_days(attendance or {})
    grade_bands = attendance_logic.get("grade_bands")
    score = _score_from_grade_bands(grade_bands, absence_days)
    if score is None:
        score = full_score if absence_days <= 0 else None
    if score is None:
        return None
    return {
        "attendance_score": round(score, 4),
        "attendance_full_score": round(full_score, 4),
        "attendance_absence_days": round(absence_days, 4),
    }


def _attendance_absence_days(attendance: dict[str, Any]) -> float:
    direct_days = sum(_number_or_zero(attendance.get(key)) for key in _ABSENCE_KEYS)
    event_count = sum(_number_or_zero(attendance.get(key)) for key in _EVENT_KEYS)
    return direct_days + event_count / 3.0


def _score_from_grade_bands(grade_bands: Any, absence_days: float) -> float | None:
    if not isinstance(grade_bands, dict):
        return None
    for band in grade_bands.values():
        if not isinstance(band, dict):
            continue
        range_text = str(band.get("absence") or "")
        if _absence_range_matches(range_text, absence_days):
            return _first_number(band.get("score"))
    return None


def _absence_range_matches(range_text: str, absence_days: float) -> bool:
    text = range_text.replace(" ", "")
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return False
    if "이하" in text:
        return absence_days <= numbers[0]
    if "미만" in text:
        return absence_days < numbers[0]
    if "이상" in text:
        return absence_days >= numbers[0]
    if "초과" in text:
        return absence_days > numbers[0]
    if len(numbers) >= 2:
        return numbers[0] <= absence_days <= numbers[1]
    return absence_days == numbers[0]


def _number_or_zero(value: Any) -> float:
    number = _first_number(value)
    return number if number is not None else 0.0
