"""Data models for Governance OS dispatch decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DispatchAction = Literal["allow", "rewrite"]


@dataclass(frozen=True)
class DispatchDecision:
    action: DispatchAction
    playbook_key: str = ""
    domain: str = ""
    confidence: float = 0.0
    matched_triggers: tuple[str, ...] = field(default_factory=tuple)
    missing_context: tuple[str, ...] = field(default_factory=tuple)
    required_tools: tuple[str, ...] = field(default_factory=tuple)
    forbidden_tools: tuple[str, ...] = field(default_factory=tuple)
    agent_chain: tuple[str, ...] = field(default_factory=tuple)
    review_gates: tuple[str, ...] = field(default_factory=tuple)
    retry_policy: str = ""
    delivery_format: str = ""
    reason: str = ""
    routing_source: str = "candidate_scorer"


@dataclass(frozen=True)
class RouteCandidate:
    score: float
    playbook_key: str
    matched_triggers: tuple[str, ...] = field(default_factory=tuple)
