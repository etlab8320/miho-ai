"""Structured decision checks for the academy LLM router."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any


ACADEMY_DOMAIN = "academy_ops"


def reject_execute_reason(
    decision: dict[str, Any],
    *,
    allowed_tools: Collection[str],
    min_confidence: float,
) -> str:
    """Return an allow-route reason when the LLM decision is not executable."""
    if decision.get("action") != "execute":
        return "not_academy"
    if _confidence(decision) < min_confidence:
        return "low_confidence"
    if str(decision.get("domain") or "").strip() != ACADEMY_DOMAIN:
        return "domain_not_academy"
    if _is_ambiguous(decision):
        return "ambiguous_academy_intent"
    if str(decision.get("tool") or "").strip() not in allowed_tools:
        return "unknown_tool"
    if not _has_semantic_intent(decision):
        return "missing_semantic_intent"
    if not _has_evidence(decision):
        return "missing_academy_evidence"
    return ""


def _confidence(payload: dict[str, Any]) -> float:
    try:
        return float(payload.get("confidence", 0))
    except (TypeError, ValueError):
        return 0.0


def _is_ambiguous(decision: dict[str, Any]) -> bool:
    value = decision.get("ambiguous", decision.get("ambiguity"))
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "yes", "1", "ambiguous"}


def _has_semantic_intent(decision: dict[str, Any]) -> bool:
    intent = decision.get("intent")
    if isinstance(intent, dict):
        return any(str(value or "").strip() for value in intent.values())
    return bool(str(intent or "").strip())


def _has_evidence(decision: dict[str, Any]) -> bool:
    evidence = decision.get("evidence")
    if not isinstance(evidence, list):
        return False
    return any(str(item or "").strip() for item in evidence)
