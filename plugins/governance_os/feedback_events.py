"""User feedback events for Governance OS Self-Harness mining."""

from __future__ import annotations

from typing import Any

from .ledger import OutcomeLedgerEntry, record_outcome


def build_quality_failure_entry(
    *,
    request_id: str,
    playbook_key: str,
    failure_signature: str,
    user_feedback: str,
    artifact_paths: tuple[str, ...] = (),
    tools_used: tuple[str, ...] = (),
    duration_ms: int = 0,
    agent_chain: tuple[str, ...] = ("user_feedback_monitor", "self_harness_signal"),
) -> OutcomeLedgerEntry:
    return OutcomeLedgerEntry(
        request_id=str(request_id or "").strip(),
        playbook_key=str(playbook_key or "").strip(),
        agent_chain=agent_chain,
        tools_used=tools_used,
        duration_ms=int(duration_ms or 0),
        review_status="user_reported_failure",
        failures=(str(failure_signature or "").strip(),),
        artifact_paths=artifact_paths,
        user_feedback=str(user_feedback or "").strip(),
    )


def record_quality_failure(
    *,
    request_id: str,
    playbook_key: str,
    failure_signature: str,
    user_feedback: str,
    artifact_paths: tuple[str, ...] = (),
    tools_used: tuple[str, ...] = (),
    duration_ms: int = 0,
    agent_chain: tuple[str, ...] = ("user_feedback_monitor", "self_harness_signal"),
) -> dict[str, Any]:
    return record_outcome(
        build_quality_failure_entry(
            request_id=request_id,
            playbook_key=playbook_key,
            failure_signature=failure_signature,
            user_feedback=user_feedback,
            artifact_paths=artifact_paths,
            tools_used=tools_used,
            duration_ms=duration_ms,
            agent_chain=agent_chain,
        )
    )
