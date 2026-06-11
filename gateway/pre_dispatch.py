"""Decision policy for pre_gateway_dispatch hook results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_DECISIVE_ACTIONS = {"skip", "respond", "rewrite"}


@dataclass(frozen=True)
class PreDispatchCandidate:
    action: str
    text: str | None = None
    route: str = ""
    reason: str = ""
    intent: str = ""
    confidence: float = 0.0
    evidence: tuple[str, ...] = field(default_factory=tuple)
    required_tool: str = ""
    priority: int = 0
    order: int = 0


@dataclass(frozen=True)
class PreDispatchDecision:
    action: str = "allow"
    text: str | None = None
    route: str = ""
    reason: str = ""
    intent: str = ""
    confidence: float = 0.0
    evidence: tuple[str, ...] = field(default_factory=tuple)
    required_tool: str = ""
    priority: int = 0
    candidates: tuple[PreDispatchCandidate, ...] = field(default_factory=tuple)


def resolve_pre_gateway_dispatch(results: list[Any]) -> PreDispatchDecision:
    candidates = tuple(_candidate_from_result(result, index) for index, result in enumerate(results))
    decisive = [candidate for candidate in candidates if candidate.action in _DECISIVE_ACTIONS]
    if not decisive:
        return PreDispatchDecision(candidates=candidates)
    chosen = max(decisive, key=lambda candidate: (candidate.priority, candidate.confidence, -candidate.order))
    return PreDispatchDecision(
        action=chosen.action,
        text=chosen.text,
        route=chosen.route,
        reason=chosen.reason,
        intent=chosen.intent,
        confidence=chosen.confidence,
        evidence=chosen.evidence,
        required_tool=chosen.required_tool,
        priority=chosen.priority,
        candidates=candidates,
    )


def _candidate_from_result(result: Any, order: int) -> PreDispatchCandidate:
    if not isinstance(result, dict):
        return PreDispatchCandidate(action="", order=order)
    action = str(result.get("action") or "").strip()
    return PreDispatchCandidate(
        action=action,
        text=result.get("text") if isinstance(result.get("text"), str) else None,
        route=str(result.get("route") or result.get("plugin") or ""),
        reason=str(result.get("reason") or ""),
        intent=str(result.get("intent") or ""),
        confidence=_confidence_value(result.get("confidence")),
        evidence=_evidence_values(result.get("evidence")),
        required_tool=str(result.get("required_tool") or ""),
        priority=_priority_value(result.get("priority")),
        order=order,
    )


def _priority_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _confidence_value(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(max(confidence, 0.0), 1.0)


def _evidence_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value if str(item or "").strip())
