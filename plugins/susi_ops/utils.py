"""Small parsing helpers shared by 수시 calculation modules."""

from __future__ import annotations

from typing import Any


def _first_number(value: Any) -> float | None:
    import re

    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    try:
        return float(match.group()) if match else None
    except ValueError:
        return None


def _optional_positive_int(value: Any) -> int | None:
    """Return a positive integer if value is numeric; otherwise None.

    Some imported 2027 rule rows use prose such as "PDF 미명시(상한 없음)" for
    fields like max_career_subjects. Treat those as an unspecified cap instead
    of crashing the recommendation engine.
    """
    if value is None or value == "":
        return None
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
