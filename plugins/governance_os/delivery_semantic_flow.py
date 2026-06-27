"""Semantic delivery judge flow for the final delivery gate."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .semantic_delivery_judge import SemanticDeliveryVerdict, judge_delivery_semantics


def delivery_evidence(decision: Any, *, context: dict[str, Any], outcomes: Any) -> dict[str, Any]:
    return {
        "decision": {
            "action": decision.action,
            "reason": decision.reason,
            "playbook_key": decision.playbook_key,
            "retry_tools": list(decision.retry_tools),
        },
        "governance_outcomes": outcomes if isinstance(outcomes, list | tuple) else [],
        "platform": str(context.get("platform") or ""),
        "session_id": str(context.get("session_id") or ""),
        "final_delivery_agent_scope": "universal",
        "runtime_semantic_signal_is_advisory": True,
    }


def semantic_agent_verdict(
    *,
    question: str,
    answer: str,
    decision: Any,
    context: dict[str, Any],
    outcomes: Any,
) -> SemanticDeliveryVerdict | None:
    if decision.reason == "internal_guard_leak":
        return None
    if not _needs_semantic_agent_verdict(decision):
        return None
    evidence = delivery_evidence(decision, context=context, outcomes=outcomes)
    evidence["semantic_judge_contract"] = {
        "python_markers_are_advisory": True,
        "python_review_context_is_advisory": True,
        "python_non_result_deferral_is_advisory": True,
        "hard_internal_leak_overrides_agent": True,
    }
    return judge_delivery_semantics(
        question=question,
        answer=answer,
        evidence=evidence,
        call_llm=context.get("semantic_delivery_call_llm"),
        extract_content=context.get("semantic_delivery_extract_content"),
    )


def decision_from_semantic_verdict(
    decision: Any,
    verdict: SemanticDeliveryVerdict | None,
    *,
    decision_factory: Callable[..., Any],
) -> Any:
    if verdict is None or verdict.action == "abstain":
        return decision
    if verdict.action == "allow":
        return decision_factory(
            action="allow",
            reason=f"agent_semantic_allow:{verdict.reason}",
            playbook_key=verdict.playbook_key or decision.playbook_key,
        )
    return decision_factory(
        action="block",
        reason=f"agent_semantic_block:{verdict.reason}",
        playbook_key=verdict.playbook_key or decision.playbook_key,
        retry_tools=verdict.retry_tools or decision.retry_tools,
    )


def _needs_semantic_agent_verdict(decision: Any) -> bool:
    if decision.action == "block":
        return True
    return decision.reason in {
        "governance_review_context",
        "not_final_delivery_claim",
        "review_evidence_passed",
    }
