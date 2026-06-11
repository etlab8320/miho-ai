"""Memory-backed policy helpers for gateway routing decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ToolCandidate(Protocol):
    action: str
    route: str
    intent: str
    confidence: float
    evidence: tuple[str, ...]
    required_tool: str
    priority: int
    order: int


@dataclass(frozen=True)
class DecisionTwinProfile:
    """Per-turn routing memory policy.

    The policy reads plugin-provided structured metadata only. It does not
    inspect user text, so domain plugins remain responsible for semantic intent
    detection and evidence collection.
    """

    prefer_required_tool_candidates: bool = True
    min_required_tool_confidence: float = 0.7
    memory_evidence: tuple[str, ...] = field(default_factory=lambda: ("owner_memory:tool_first",))


@dataclass(frozen=True)
class DecisionTwinChoice:
    candidate: ToolCandidate
    state: str
    memory_evidence: tuple[str, ...]
    policy_violations: tuple[str, ...] = ()


def choose_decision_twin_candidate(
    candidates: list[ToolCandidate],
    profile: DecisionTwinProfile | None = None,
) -> DecisionTwinChoice | None:
    """Choose a decisive candidate using memory-backed tool-first policy."""
    if not candidates:
        return None
    policy = profile or DecisionTwinProfile()
    if policy.prefer_required_tool_candidates:
        required = [
            candidate
            for candidate in candidates
            if _is_required_tool_candidate(candidate, policy)
        ]
        if required:
            chosen = _rank(required)
            return DecisionTwinChoice(
                candidate=chosen,
                state="required_tool_first",
                memory_evidence=_memory_evidence_for(chosen, policy),
            )
    chosen = _rank(candidates)
    return DecisionTwinChoice(
        candidate=chosen,
        state="legacy_rank",
        memory_evidence=policy.memory_evidence,
        policy_violations=_policy_violations(chosen, candidates, policy),
    )


def _is_required_tool_candidate(candidate: ToolCandidate, profile: DecisionTwinProfile) -> bool:
    if not str(candidate.required_tool or "").strip():
        return False
    return float(candidate.confidence or 0.0) >= profile.min_required_tool_confidence


def _rank(candidates: list[ToolCandidate]) -> ToolCandidate:
    return max(candidates, key=lambda candidate: (candidate.priority, candidate.confidence, -candidate.order))


def _memory_evidence_for(candidate: ToolCandidate, profile: DecisionTwinProfile) -> tuple[str, ...]:
    tool = str(candidate.required_tool or "").strip()
    if not tool:
        return profile.memory_evidence
    return (*profile.memory_evidence, f"required_tool:{tool}")


def _policy_violations(
    chosen: ToolCandidate,
    candidates: list[ToolCandidate],
    profile: DecisionTwinProfile,
) -> tuple[str, ...]:
    if str(chosen.required_tool or "").strip():
        return ()
    missed = [
        str(candidate.required_tool)
        for candidate in candidates
        if _is_required_tool_candidate(candidate, profile)
    ]
    if not missed:
        return ()
    unique = sorted(set(missed))
    return tuple(f"missed_required_tool:{tool}" for tool in unique)
