"""Variable comparison helpers for sports performance reports."""

from __future__ import annotations

import re
from typing import Any

_VALUE_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")
_SIGNED_MAGNITUDE_KEYS = {
    "arm_backswing_angle",
    "descent_velocity",
}


def display_measure(key: str, value: Any, unit: Any = "") -> str:
    number = numeric_value(key, value)
    if number is None:
        return str(value or "").strip()
    return f"{number:.2f} {str(unit or '').strip()}".strip()


def numeric_value(key: str, value: Any) -> float | None:
    raw = _raw_number(value)
    if raw is None:
        return None
    if key in _SIGNED_MAGNITUDE_KEYS:
        return abs(raw)
    return raw


def comparison_pair(key: str, current: Any, elite: Any) -> tuple[float | None, float | None]:
    return numeric_value(key, current), numeric_value(key, elite)


def display_unit(value: Any) -> str:
    text = str(value or "").strip()
    match = _VALUE_PATTERN.search(text)
    return text[match.end():].strip() if match else ""


def _raw_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    match = _VALUE_PATTERN.search(text)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None
