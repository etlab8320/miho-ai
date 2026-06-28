"""Runtime feedback bridge for Governance OS Self-Harness."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .feedback_events import record_quality_failure
from .runtime_learning import record_runtime_learning
from .self_harness_loop import (
    ContentExtractor,
    LlmCaller,
    ReceiptRunner,
    run_self_harness_autopilot,
)

RUNTIME_FEEDBACK_LOOP_SCHEMA = "miho-self-harness/runtime-feedback-loop/v1"


def run_feedback_improvement_loop(
    *,
    request_id: str,
    playbook_key: str,
    failure_signature: str,
    user_feedback: str,
    artifact_paths: tuple[str, ...] = (),
    tools_used: tuple[str, ...] = (),
    recent_events: Iterable[dict[str, Any]] = (),
    min_recurrence: int = 2,
    receipt_runner: ReceiptRunner | None = None,
    smoke_runner: ReceiptRunner | None = None,
    call_llm: LlmCaller | None = None,
    extract_content: ContentExtractor | None = None,
    max_activations: int | None = 1,
    record_failure: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Record user-reported failure and immediately run Self-Harness.

    This is not a user-facing fallback. It is the runtime bridge from "user says
    the result is bad" to "ledger event + LLM miner/proposer + receipts +
    activation/rollback smoke" in the same process.
    """

    recorder = record_failure or record_quality_failure
    event = recorder(
        request_id=request_id,
        playbook_key=playbook_key,
        failure_signature=failure_signature,
        user_feedback=user_feedback,
        artifact_paths=artifact_paths,
        tools_used=tools_used,
    )
    events = [*list(recent_events), event]
    autopilot = run_self_harness_autopilot(
        events=events,
        min_recurrence=min_recurrence,
        receipt_runner=receipt_runner,
        smoke_runner=smoke_runner,
        call_llm=call_llm,
        extract_content=extract_content,
        max_activations=max_activations,
    )
    learning = record_runtime_learning(
        request_id=request_id,
        playbook_key=playbook_key,
        failure_signature=failure_signature,
        user_feedback=user_feedback,
        artifact_paths=artifact_paths,
        tools_used=tools_used,
        autopilot=autopilot,
    )
    return {
        "schema_version": RUNTIME_FEEDBACK_LOOP_SCHEMA,
        "status": _status_from_autopilot(autopilot),
        "recorded_event_id": int(event.get("id") or 0),
        "self_harness_triggered": True,
        "user_visible_message_allowed": False,
        "runtime_learning": learning,
        "autopilot": autopilot,
    }


def _status_from_autopilot(autopilot: dict[str, Any]) -> str:
    if autopilot.get("rolled_back"):
        return "rolled_back"
    if autopilot.get("activated"):
        return "activated"
    if autopilot.get("errors"):
        return "error"
    if autopilot.get("skipped_unsafe"):
        return "skipped_unsafe"
    return "held"
