"""Agentic exception recovery for the Governance OS final delivery hook."""

from __future__ import annotations

import logging
from typing import Any

from .final_delivery_current_result import compose_current_result
from .final_delivery_recovery import recover_blocked_delivery
from .semantic_delivery_judge import SemanticDeliveryVerdict, judge_delivery_semantics

logger = logging.getLogger(__name__)


def recover_transform_exception(*, response_text: str, context: dict[str, Any]) -> str | None:
    """Recover a hook exception through the semantic judge, not candidate gates."""

    user_text = str(context.get("user_message") or context.get("user_text") or "")
    original_text = str(response_text or "")
    if not original_text.strip():
        return None

    verdict = _semantic_exception_verdict(
        question=user_text,
        answer=original_text,
        context=context,
    )
    if verdict is not None and verdict.action == "allow":
        return None

    evidence = _exception_evidence(verdict=verdict, context=context)
    try:
        recovered = recover_blocked_delivery(
            question=user_text,
            answer=original_text,
            evidence=evidence,
            call_llm=context.get("final_delivery_call_llm"),
            extract_content=context.get("final_delivery_extract_content"),
        )
    except Exception as exc:
        logger.warning("governance hook exception recovery failed closed: %s", exc)
        return _limited_current_result(evidence)
    return recovered or _limited_current_result(evidence)


def _semantic_exception_verdict(
    *,
    question: str,
    answer: str,
    context: dict[str, Any],
) -> SemanticDeliveryVerdict | None:
    evidence = {
        "decision": {
            "action": "review",
            "reason": "final_delivery_hook_exception",
        },
        "hook_exception_recovery": True,
        "semantic_judge_required": True,
        "runtime_signals_are_advisory": True,
        "candidate_gate_removed": True,
        "session_id": str(context.get("session_id") or ""),
    }
    return judge_delivery_semantics(
        question=question,
        answer=answer,
        evidence=evidence,
        call_llm=context.get("semantic_delivery_call_llm"),
        extract_content=context.get("semantic_delivery_extract_content"),
    )


def _exception_evidence(
    *,
    verdict: SemanticDeliveryVerdict | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    retry_tools = tuple(str(tool) for tool in context.get("retry_tools") or ())
    playbook_key = ""
    reason = "agent_semantic_unavailable"

    if verdict is not None:
        playbook_key = verdict.playbook_key
        retry_tools = verdict.retry_tools or retry_tools
        if verdict.action == "block":
            reason = f"agent_semantic_block:{verdict.reason}"
        else:
            reason = f"agent_semantic_abstain:{verdict.reason}"

    return {
        "decision": {
            "action": "block",
            "reason": reason,
            "playbook_key": playbook_key,
            "retry_tools": list(retry_tools),
        },
        "playbook_key": playbook_key,
        "retry_tools": list(retry_tools),
        "hook_exception_recovery": True,
        "semantic_delivery_verdict": verdict.action if verdict is not None else "unavailable",
        "session_id": str(context.get("session_id") or ""),
    }


def _limited_current_result(evidence: dict[str, Any]) -> str:
    return compose_current_result(evidence)
