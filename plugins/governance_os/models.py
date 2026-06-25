"""Data contracts for Miho Governance Agent OS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


AgentKind = Literal["control", "judge", "worker", "domain"]
PolicyAction = Literal["allow", "block", "review_required", "retry", "require_approval"]


def _tuple_str(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


@dataclass(frozen=True)
class AgentRole:
    key: str
    kind: AgentKind
    description: str = ""
    responsibilities: tuple[str, ...] = field(default_factory=tuple)
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    forbidden_tools: tuple[str, ...] = field(default_factory=tuple)
    review_gates: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: int = 30
    fallback_agent: str = ""

    @classmethod
    def from_mapping(cls, key: str, data: dict[str, Any]) -> "AgentRole":
        kind = str(data.get("kind") or "").strip()
        if kind not in {"control", "judge", "worker", "domain"}:
            raise ValueError(f"agent role {key!r} has invalid kind {kind!r}")
        return cls(
            key=key,
            kind=kind,  # type: ignore[arg-type]
            description=str(data.get("description") or "").strip(),
            responsibilities=_tuple_str(data.get("responsibilities")),
            allowed_tools=_tuple_str(data.get("allowed_tools")),
            forbidden_tools=_tuple_str(data.get("forbidden_tools")),
            review_gates=_tuple_str(data.get("review_gates")),
            timeout_seconds=int(data.get("timeout_seconds") or 30),
            fallback_agent=str(data.get("fallback_agent") or "").strip(),
        )


@dataclass(frozen=True)
class Playbook:
    key: str
    domain: str
    triggers: tuple[str, ...] = field(default_factory=tuple)
    required_context: tuple[str, ...] = field(default_factory=tuple)
    required_tools: tuple[str, ...] = field(default_factory=tuple)
    forbidden_tools: tuple[str, ...] = field(default_factory=tuple)
    agent_chain: tuple[str, ...] = field(default_factory=tuple)
    review_gates: tuple[str, ...] = field(default_factory=tuple)
    retry_policy: str = ""
    delivery_format: str = ""
    ledger_policy: str = ""
    memory_policy: str = ""
    rollback_policy: str = ""

    @classmethod
    def from_mapping(cls, key: str, data: dict[str, Any]) -> "Playbook":
        return cls(
            key=key,
            domain=str(data.get("domain") or "").strip(),
            triggers=_tuple_str(data.get("triggers")),
            required_context=_tuple_str(data.get("required_context")),
            required_tools=_tuple_str(data.get("required_tools")),
            forbidden_tools=_tuple_str(data.get("forbidden_tools")),
            agent_chain=_tuple_str(data.get("agent_chain")),
            review_gates=_tuple_str(data.get("review_gates")),
            retry_policy=str(data.get("retry_policy") or "").strip(),
            delivery_format=str(data.get("delivery_format") or "").strip(),
            ledger_policy=str(data.get("ledger_policy") or "").strip(),
            memory_policy=str(data.get("memory_policy") or "").strip(),
            rollback_policy=str(data.get("rollback_policy") or "").strip(),
        )


@dataclass(frozen=True)
class PolicyDecision:
    action: PolicyAction
    reason: str
    playbook_key: str = ""
    agent_key: str = ""
    tool_name: str = ""
    message_ko: str = ""
    evidence: tuple[str, ...] = field(default_factory=tuple)
    review_gates: tuple[str, ...] = field(default_factory=tuple)
