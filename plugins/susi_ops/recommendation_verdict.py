"""Deterministic verdict labels for susi recommendation candidates."""

from __future__ import annotations


PRACTICAL_RATE_FIT_MAX = 85.0
MARGIN_FIT_MIN = 50.0
PRACTICAL_MARGIN_RATE_FIT_MIN = 6.0


def practical_verdict(
    needed_practical_rate_pct: float | None,
    *,
    margin_at_full_practical: float | None = None,
    practical_max: float | None = None,
) -> str:
    """Return the fixed two-label 상담 verdict used in PDF/report output."""
    if needed_practical_rate_pct is None:
        return "상향"
    if needed_practical_rate_pct <= PRACTICAL_RATE_FIT_MAX:
        return "적정"
    if margin_at_full_practical is not None and margin_at_full_practical >= MARGIN_FIT_MIN:
        return "적정"
    if margin_at_full_practical is not None and practical_max and practical_max > 0:
        margin_rate = margin_at_full_practical / practical_max * 100
        if margin_rate >= PRACTICAL_MARGIN_RATE_FIT_MIN:
            return "적정"
    return "상향"
