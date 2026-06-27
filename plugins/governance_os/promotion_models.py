"""Data models for Governance OS promotion candidates and activations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PromotionAction = Literal["add_forbidden_tool", "add_required_tool", "add_review_gate"]


@dataclass(frozen=True)
class PromotionCandidate:
    playbook_key: str
    source_failure: str
    recurrence_count: int
    proposed_policy: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    tests_required: tuple[str, ...] = field(default_factory=tuple)
    rollback: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return {
            "playbook_key": self.playbook_key,
            "source_failure": self.source_failure,
            "recurrence_count": int(self.recurrence_count),
            "proposed_policy": self.proposed_policy,
            "evidence": list(self.evidence),
            "tests_required": list(self.tests_required),
            "rollback": self.rollback,
        }


@dataclass(frozen=True)
class PromotionActivation:
    playbook_key: str
    action: PromotionAction
    value: str
    snapshot_id: str
    rollback_snapshot_id: str
    fingerprint: str
    event_id: int

    def to_metadata(self) -> dict[str, Any]:
        return {
            "playbook_key": self.playbook_key,
            "action": self.action,
            "value": self.value,
            "snapshot_id": self.snapshot_id,
            "rollback_snapshot_id": self.rollback_snapshot_id,
            "fingerprint": self.fingerprint,
            "event_id": self.event_id,
        }


@dataclass(frozen=True)
class PromotionTestReceipt:
    name: str
    passed: bool
    status: str = ""
    exit_code: int | None = None
    command: str = ""
    evidence: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "status": self.status,
            "exit_code": self.exit_code,
            "command": self.command,
            "evidence": self.evidence,
        }
