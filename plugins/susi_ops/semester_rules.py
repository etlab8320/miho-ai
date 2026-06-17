"""Semester inclusion rules for Susi score formulas."""

from __future__ import annotations

import re
from typing import Any


def is_graduate_context(student_context: dict[str, Any] | None) -> bool:
    if not isinstance(student_context, dict):
        return False
    values = [
        student_context.get("graduation_status"),
        student_context.get("student_status"),
        student_context.get("졸업구분"),
        student_context.get("재학구분"),
    ]
    truthy = {"graduate", "graduated", "alumni", "n수생", "졸업", "졸업자"}
    if any(str(value or "").strip().lower() in truthy for value in values):
        return True
    return bool(student_context.get("is_graduate") or student_context.get("졸업자"))


def within_semester_limit(
    row: dict[str, Any],
    limit: Any,
    student_context: dict[str, Any] | None = None,
) -> bool:
    """Return whether a grade row is within the formula's semester scope."""
    text = str(limit or "")
    if not text:
        return True
    if is_graduate_context(student_context) and _graduate_gets_all_years(text):
        return True
    matches = re.findall(r"(\d)\s*학년\s*(\d)\s*학기", text)
    if not matches:
        return True
    end_yr, end_sem = int(matches[-1][0]), int(matches[-1][1])
    try:
        yr = int(row.get("학년"))
        sem = int(row.get("학기"))
    except (TypeError, ValueError):
        return True
    return yr < end_yr or (yr == end_yr and sem <= end_sem)


def _graduate_gets_all_years(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text)
    return "졸업자:전학년" in normalized or "졸업자는전학년" in normalized
