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
    priority: int = 0
    order: int = 0


@dataclass(frozen=True)
class PreDispatchDecision:
    action: str = "allow"
    text: str | None = None
    route: str = ""
    reason: str = ""
    priority: int = 0
    candidates: tuple[PreDispatchCandidate, ...] = field(default_factory=tuple)


def resolve_pre_gateway_dispatch(results: list[Any]) -> PreDispatchDecision:
    candidates = tuple(_candidate_from_result(result, index) for index, result in enumerate(results))
    decisive = [candidate for candidate in candidates if candidate.action in _DECISIVE_ACTIONS]
    if not decisive:
        return PreDispatchDecision(candidates=candidates)
    chosen = max(decisive, key=lambda candidate: (candidate.priority, -candidate.order))
    return PreDispatchDecision(
        action=chosen.action,
        text=chosen.text,
        route=chosen.route,
        reason=chosen.reason,
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
        priority=_priority_value(result.get("priority")),
        order=order,
    )


def _priority_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
