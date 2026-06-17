"""Score adjustment helpers for official Susi formula edge cases."""

from __future__ import annotations

import json
from typing import Any


def achievement_ratio_grade(row: dict[str, Any], achievement: str | None) -> float | None:
    """Return grade from an achievement-ratio table, or None when unavailable.

    Some guides, including Konkuk GLOCAL, do not use fixed B/C grades for
    career subjects. They map B to the B+C achievement ratio and C to the C
    achievement ratio, then convert that ratio to a 9-grade band.
    """
    ach = str(achievement or "").strip().upper()
    if ach == "A":
        return 1.0
    if ach not in {"B", "C"}:
        return None

    ratios = _achievement_ratios(row)
    if ratios is None:
        return None
    ratio = ratios.get("C") if ach == "C" else ratios.get("B", 0.0) + ratios.get("C", 0.0)
    return _grade_from_ratio(ratio) if ratio is not None else None


def apply_unit_shortfall_adjustment(
    record_score: float,
    total_units: float,
    score_logic: dict[str, Any],
) -> float:
    config = score_logic.get("unit_shortfall_adjustment")
    if not isinstance(config, dict):
        return record_score

    threshold = _float_or_none(config.get("threshold_units"))
    if threshold is None or total_units >= threshold:
        return record_score

    base_factor = _float_or_none(config.get("base_factor"))
    per_missing = _float_or_none(config.get("per_missing_unit"))
    if base_factor is None:
        base_factor = 1.0
    if per_missing is None:
        per_missing = 0.0

    missing_units = threshold - total_units
    return record_score * (base_factor - missing_units * per_missing)


def uses_achievement_ratio_grade(score_logic: dict[str, Any]) -> bool:
    strategy = str(score_logic.get("career_conversion_strategy") or "").strip().lower()
    return strategy in {"achievement_ratio_grade", "achievement_ratio", "성취도비율"}


def _achievement_ratios(row: dict[str, Any]) -> dict[str, float] | None:
    value = row.get("achievement_ratios") or row.get("성취도별비율")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None

    ratios: dict[str, float] = {}
    for key in ("A", "B", "C"):
        parsed = _float_or_none(value.get(key) or value.get(key.lower()) or value.get(f"{key}비율"))
        if parsed is not None:
            ratios[key] = parsed
    return ratios if ratios else None


def _grade_from_ratio(ratio: float) -> float:
    if ratio >= 96:
        return 1.0
    if ratio >= 89:
        return 2.0
    if ratio >= 77:
        return 3.0
    if ratio >= 60:
        return 4.0
    if ratio >= 40:
        return 5.0
    if ratio >= 23:
        return 6.0
    if ratio >= 11:
        return 7.0
    if ratio >= 4:
        return 8.0
    return 9.0


def _float_or_none(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
