"""Small Korean date parser for academy operations."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any


_KOREAN_DATE_RE = re.compile(
    r"(?:(?P<year>\d{4})\s*년\s*)?(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일"
)
_NUMERIC_MONTH_DAY_RE = re.compile(
    r"(?<!\d)(?P<month>\d{1,2})\s*[/.]\s*(?P<day>\d{1,2})(?!\d)"
)


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
        pass
    parsed = _parse_korean_date(text, base)
    if parsed is not None:
        return parsed
    parsed = _parse_numeric_month_day(text, base)
    if parsed is not None:
        return parsed
    return base


def _parse_korean_date(text: str, base: date) -> date | None:
    match = _KOREAN_DATE_RE.search(text)
    if match is None:
        return None
    year = int(match.group("year") or base.year)
    return _build_date(year, int(match.group("month")), int(match.group("day")))


def _parse_numeric_month_day(text: str, base: date) -> date | None:
    match = _NUMERIC_MONTH_DAY_RE.search(text)
    if match is None:
        return None
    return _build_date(base.year, int(match.group("month")), int(match.group("day")))


def _build_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
