"""Small Korean date parser for academy operations."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def parse_academy_date(value: Any = None, *, today: date | None = None) -> date:
    base = today or date.today()
    text = str(value or "").strip()
    if not text:
        return base
    lowered = text.lower()
    if "그제" in lowered or "그저께" in lowered:
        return base - timedelta(days=2)
    if "어제" in lowered:
        return base - timedelta(days=1)
    if "내일" in lowered:
        return base + timedelta(days=1)
    if "오늘" in lowered:
        return base
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return base
