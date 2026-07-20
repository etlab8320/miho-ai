"""Gender eligibility checks for recommendation candidates."""

from __future__ import annotations

from typing import Any


def gender_key(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if text in {"m", "male", "man", "boy", "남", "남자", "남학생"}:
        return "male"
    if text in {"f", "female", "woman", "girl", "여", "여자", "여학생"}:
        return "female"
    if any(marker in text for marker in ("남자", "남학생", " male", "boy")):
        return "male"
    if any(marker in text for marker in ("여자", "여학생", " female", "girl")):
        return "female"
    return ""


def is_gender_ineligible(university: Any, department: Any, key: str) -> bool:
    if key != "male":
        return False
    text = f"{university or ''} {department or ''}"
    return any(marker in text for marker in ("여자대학교", "여대", "여자대학"))


__all__ = ["gender_key", "is_gender_ineligible"]
