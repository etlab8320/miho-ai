"""Outcome ledger bridge for Governance OS."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class OutcomeLedgerEntry:
    request_id: str
    playbook_key: str
    agent_chain: tuple[str, ...] = field(default_factory=tuple)
    tools_used: tuple[str, ...] = field(default_factory=tuple)
    duration_ms: int = 0
    review_status: str = ""
    failures: tuple[str, ...] = field(default_factory=tuple)
    retry_tools: tuple[str, ...] = field(default_factory=tuple)
    artifact_paths: tuple[str, ...] = field(default_factory=tuple)
    user_feedback: str = ""
    promotion_candidates: tuple[str, ...] = field(default_factory=tuple)
    created_at: str = ""

    def to_metadata(self) -> dict[str, Any]:
        created_at = self.created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "request_id": self.request_id,
            "playbook_key": self.playbook_key,
            "agent_chain": list(self.agent_chain),
            "tools_used": list(self.tools_used),
            "duration_ms": int(self.duration_ms or 0),
            "review_status": self.review_status,
            "failures": list(self.failures),
            "retry_tools": list(self.retry_tools),
            "artifact_paths": list(self.artifact_paths),
            "user_feedback": self.user_feedback,
            "promotion_candidates": list(self.promotion_candidates),
            "created_at": created_at,
        }


def record_outcome(entry: OutcomeLedgerEntry) -> dict[str, Any]:
    if not entry.request_id.strip():
        raise ValueError("request_id is required")
    if not entry.playbook_key.strip():
        raise ValueError("playbook_key is required")

    from agent import evolution

    metadata = entry.to_metadata()
    failures = metadata["failures"]
    summary = _summary(metadata)
    return evolution.record_event(
        kind="note",
        title=f"Governance outcome {entry.playbook_key}",
        summary=summary,
        status="failed" if failures else "recorded",
        metadata={"governance_outcome": metadata},
    )


def list_outcomes(
    *,
    limit: int = 20,
    playbook_key: str = "",
) -> list[dict[str, Any]]:
    from agent import evolution

    clean_playbook = str(playbook_key or "").strip()
    outcomes: list[dict[str, Any]] = []
    for event in evolution.list_events(limit=max(1, int(limit))):
        outcome = _governance_outcome(event)
        if outcome is None:
            continue
        if clean_playbook and outcome.get("playbook_key") != clean_playbook:
            continue
        item = dict(outcome)
        item["event_id"] = int(event.get("id") or 0)
        item["event_status"] = str(event.get("status") or "")
        item["event_created_at"] = str(event.get("created_at") or "")
        outcomes.append(item)
    return outcomes


def _summary(metadata: dict[str, Any]) -> str:
    status = str(metadata.get("review_status") or "unknown")
    tools = ", ".join(str(item) for item in metadata.get("tools_used") or [])
    failures = metadata.get("failures") or []
    failure_text = f" failures={len(failures)}" if failures else ""
    tools_text = f" tools={tools}" if tools else ""
    return f"review_status={status}{tools_text}{failure_text}".strip()


def _governance_outcome(event: dict[str, Any]) -> dict[str, Any] | None:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return None
    outcome = metadata.get("governance_outcome")
    return outcome if isinstance(outcome, dict) else None
