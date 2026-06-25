"""Agent Council execution contract for Governance OS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .dispatcher import DispatchDecision, dispatch_request
from .ledger import OutcomeLedgerEntry, record_outcome
from .models import PolicyDecision
from .policy import evaluate_tool_call
from .registry import GovernanceRegistry
from .review import (
    ReviewGateOutcome,
    auxiliary_review_policy_for_playbook,
    evaluate_review_gate,
)
from .risk import evaluate_request_risk
from .versioning import load_runtime_registry


CouncilStatus = Literal[
    "allowed",
    "blocked",
    "passed",
    "retry",
    "needs_human_review",
    "review_required",
    "approval_required",
]
CouncilAction = Literal["allow", "block", "deliver", "retry", "hold"]


@dataclass(frozen=True)
class CouncilTurnResult:
    status: CouncilStatus
    action: CouncilAction
    playbook_key: str = ""
    message_ko: str = ""
    dispatch: DispatchDecision | None = None
    policy: PolicyDecision | None = None
    review: ReviewGateOutcome | None = None
    ledger_event: dict[str, Any] | None = None
    failures: tuple[str, ...] = field(default_factory=tuple)
    retry_tools: tuple[str, ...] = field(default_factory=tuple)


def run_council_turn(
    *,
    request_id: str,
    user_text: str,
    tool_name: str,
    tool_result: Any = None,
    tool_args: dict[str, Any] | None = None,
    available_context: tuple[str, ...] = (),
    duration_ms: int = 0,
    artifact_paths: tuple[str, ...] = (),
    user_feedback: str = "",
    registry: GovernanceRegistry | None = None,
    record_ledger: bool = True,
) -> CouncilTurnResult:
    active_registry = registry or load_runtime_registry()
    dispatch = dispatch_request(
        active_registry,
        user_text,
        available_context=available_context,
    )
    if not dispatch.playbook_key:
        return CouncilTurnResult(status="allowed", action="allow", dispatch=dispatch)

    risk = evaluate_request_risk(
        active_registry,
        playbook_key=dispatch.playbook_key,
        user_text=user_text,
        available_context=available_context,
        tool_name=tool_name,
        args=tool_args,
    )
    if risk.action == "require_approval":
        return _record_and_result(
            request_id=request_id,
            dispatch=dispatch,
            policy=risk,
            status="approval_required",
            action="hold",
            review_status="approval_required",
            failures=(risk.reason,),
            message_ko=risk.message_ko,
            tool_name=tool_name,
            duration_ms=duration_ms,
            artifact_paths=artifact_paths,
            user_feedback=user_feedback,
            record_ledger=record_ledger,
        )

    policy = evaluate_tool_call(
        active_registry,
        playbook_key=dispatch.playbook_key,
        tool_name=tool_name,
        args=tool_args,
    )
    if policy.action == "block":
        return _record_and_result(
            request_id=request_id,
            dispatch=dispatch,
            policy=policy,
            status="blocked",
            action="block",
            review_status="blocked",
            failures=(policy.reason,),
            message_ko=policy.message_ko,
            tool_name=tool_name,
            duration_ms=duration_ms,
            artifact_paths=artifact_paths,
            user_feedback=user_feedback,
            record_ledger=record_ledger,
        )

    if policy.action == "review_required" and tool_result is None:
        return _record_and_result(
            request_id=request_id,
            dispatch=dispatch,
            policy=policy,
            status="review_required",
            action="hold",
            review_status="review_required",
            failures=(),
            message_ko=policy.message_ko,
            tool_name=tool_name,
            duration_ms=duration_ms,
            artifact_paths=artifact_paths,
            user_feedback=user_feedback,
            record_ledger=record_ledger,
        )

    review = evaluate_review_gate(
        active_registry,
        playbook_key=dispatch.playbook_key,
        tool_name=tool_name,
        result=tool_result,
        auxiliary_review_policy=auxiliary_review_policy_for_playbook(dispatch.playbook_key),
    )
    if review.status == "pass":
        return _record_and_result(
            request_id=request_id,
            dispatch=dispatch,
            policy=policy,
            review=review,
            status="passed",
            action="deliver",
            review_status="pass",
            failures=(),
            message_ko="",
            tool_name=tool_name,
            duration_ms=duration_ms,
            artifact_paths=artifact_paths,
            user_feedback=user_feedback,
            record_ledger=record_ledger,
        )
    if review.status == "needs_human_review":
        return _record_and_result(
            request_id=request_id,
            dispatch=dispatch,
            policy=policy,
            review=review,
            status="needs_human_review",
            action="hold",
            review_status="needs_human_review",
            failures=(review.reason,),
            message_ko=review.message_ko,
            tool_name=tool_name,
            duration_ms=duration_ms,
            artifact_paths=artifact_paths,
            user_feedback=user_feedback,
            record_ledger=record_ledger,
        )
    return _record_and_result(
        request_id=request_id,
        dispatch=dispatch,
        policy=policy,
        review=review,
        status="retry",
        action="retry",
        review_status="fail",
        failures=(review.reason,),
        message_ko=review.message_ko,
        tool_name=tool_name,
        duration_ms=duration_ms,
        artifact_paths=artifact_paths,
        user_feedback=user_feedback,
        record_ledger=record_ledger,
    )


def _record_and_result(
    *,
    request_id: str,
    dispatch: DispatchDecision,
    policy: PolicyDecision,
    status: CouncilStatus,
    action: CouncilAction,
    review_status: str,
    failures: tuple[str, ...],
    message_ko: str,
    tool_name: str,
    duration_ms: int,
    artifact_paths: tuple[str, ...],
    user_feedback: str,
    record_ledger: bool,
    review: ReviewGateOutcome | None = None,
) -> CouncilTurnResult:
    event = None
    if record_ledger:
        event = record_outcome(
            OutcomeLedgerEntry(
                request_id=request_id,
                playbook_key=dispatch.playbook_key,
                agent_chain=dispatch.agent_chain,
                tools_used=(tool_name,),
                duration_ms=duration_ms,
                review_status=review_status,
                failures=failures,
                retry_tools=review.retry_tools if action == "retry" and review else (),
                artifact_paths=artifact_paths,
                user_feedback=user_feedback,
            )
        )
    return CouncilTurnResult(
        status=status,
        action=action,
        playbook_key=dispatch.playbook_key,
        message_ko=message_ko,
        dispatch=dispatch,
        policy=policy,
        review=review,
        ledger_event=event,
        failures=failures,
        retry_tools=review.retry_tools if action == "retry" and review else (),
    )
