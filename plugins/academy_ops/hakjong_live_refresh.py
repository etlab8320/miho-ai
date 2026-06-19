"""Refresh policy helpers for hakjong live research bundles."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


_SECTION_TTL_DEFAULTS = {"faculty": 168.0, "paper": 24.0, "news": 0.0}


def _env_hours(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def section_ttls() -> dict[str, float]:
    return {
        "faculty": _env_hours("MIHO_HAKJONG_FACULTY_TTL_HOURS", _SECTION_TTL_DEFAULTS["faculty"]),
        "paper": _env_hours("MIHO_HAKJONG_PAPER_TTL_HOURS", _SECTION_TTL_DEFAULTS["paper"]),
        "news": _env_hours("MIHO_HAKJONG_NEWS_TTL_HOURS", _SECTION_TTL_DEFAULTS["news"]),
    }


def _parse_dt(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def section_fresh(bundle: dict[str, Any] | None, key: str, ttl: float) -> bool:
    if ttl <= 0 or not isinstance(bundle, dict):
        return False
    raw_section = bundle.get(key)
    section_stamp = None
    if isinstance(raw_section, list) and raw_section and isinstance(raw_section[0], dict):
        section_stamp = raw_section[0].get("searched_at")
    searched = _parse_dt(section_stamp or bundle.get("searched_at"))
    if searched is None:
        return False
    age = (datetime.now(timezone.utc) - searched.astimezone(timezone.utc)).total_seconds() / 3600
    return age <= ttl


def failed_results(items: list[dict[str, Any]]) -> bool:
    return not items or all("실패" in str(item.get("title") or "") for item in items)


def copy_section(bundle: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    raw = bundle.get(key) if isinstance(bundle, dict) else None
    return [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
