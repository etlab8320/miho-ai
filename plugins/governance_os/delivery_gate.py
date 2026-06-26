"""Final response delivery gate for governed Governance OS outputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from .delivery_gate_constants import (
    ARTIFACT_COMPLETION_TERMS as _ARTIFACT_COMPLETION_TERMS,
    COMPLETION_CLAIM_MARKERS as _COMPLETION_CLAIM_MARKERS,
    DOMAIN_DELIVERY_TERMS as _DOMAIN_DELIVERY_TERMS,
    DOMAIN_VERDICT_MARKERS as _DOMAIN_VERDICT_MARKERS,
    FINAL_CLAIM_MARKERS as _FINAL_CLAIM_MARKERS,
    GOVERNANCE_REVIEW_MARKERS as _GOVERNANCE_REVIEW_MARKERS,
    META_EXPLANATION_TERMS as _META_EXPLANATION_TERMS,
    PERSONALIZED_DELIVERY_TERMS as _PERSONALIZED_DELIVERY_TERMS,
    PLAYBOOK_BY_TOOL as _PLAYBOOK_BY_TOOL,
    SCORE_CLAIM_RE as _SCORE_CLAIM_RE,
    STUDENT_SCORE_CLAIM_RE as _STUDENT_SCORE_CLAIM_RE,
)
from .delivery_media import prepare_delivery_media
from .delivery_safety import (
    contains_hard_internal_leak as _contains_hard_internal_leak,
    contains_internal_guard_leak as _shared_contains_internal_guard_leak,
    normalized_blob as _shared_normalized_blob,
)
from .dispatcher import dispatch_request
from .final_delivery_agent import review_final_delivery
from .final_delivery_recovery import recover_blocked_delivery
from .registry import GovernanceRegistry
from .review import auxiliary_review_policy_for_playbook, evaluate_review_gate
from .versioning import load_runtime_registry


FinalDeliveryAction = Literal["allow", "block"]


def _normalized_blob(text: Any) -> str:
    return _shared_normalized_blob(text)


# Admission-process-specific terms. A bare score ("95점") only force-routes to the
# academy score playbook when one of these is present, so general tech/finance
# answers that happen to mention a score are not blocked (범용성 보존).
_ADMISSION_CONTEXT_TERMS = (
    "수시",
    "정시",
    "환산",
    "내신",
    "등급컷",
    "실기",
    "학종",
    "생기부",
    "학생부",
    "전형",
    "수험생",
    "가능권",
    "모집",
    "지원 가능",
    "지원가능",
)


def _has_admission_context(text: Any) -> bool:
    blob = _normalized_blob(text)
    return any(term in blob for term in _ADMISSION_CONTEXT_TERMS)


@dataclass(frozen=True)
class FinalDeliveryDecision:
    action: FinalDeliveryAction
    reason: str
    playbook_key: str = ""
    message_ko: str = ""
    retry_tools: tuple[str, ...] = field(default_factory=tuple)


def governance_transform_llm_output(
    response_text: str = "",
    **context: Any,
) -> str | None:
    registry = load_runtime_registry()
    user_text = str(context.get("user_message") or context.get("user_text") or "")
    original_text = str(response_text or "")

    # Final Delivery Gate owns the whole attachment contract. Tool media that the
    # model omitted is appended before path repair so the gateway never receives
    # an unchecked MEDIA directive after this hook.
    media_prepared = prepare_delivery_media(
        original_text,
        context.get("conversation_history"),
        user_text=user_text,
    )
    effective_text = media_prepared if media_prepared is not None else original_text

    outcomes = context.get("governance_outcomes")
    if outcomes is None:
        outcomes = _outcomes_from_conversation_history(
            registry,
            context.get("conversation_history"),
            user_text=user_text,
        )
    decision = evaluate_final_delivery(
        registry,
        response_text=effective_text,
        user_text=user_text,
        outcomes=outcomes,
    )
    delivered = review_final_delivery(
        question=user_text,
        answer=effective_text,
        evidence=_delivery_evidence(decision, context=context, outcomes=outcomes),
        call_llm=context.get("final_delivery_call_llm"),
        extract_content=context.get("final_delivery_extract_content"),
    )
    if delivered is not None:
        return delivered
    if decision.action != "block":
        return media_prepared
    return recover_blocked_delivery(
        question=user_text,
        answer=effective_text,
        evidence=_delivery_evidence(decision, context=context, outcomes=outcomes),
        call_llm=context.get("final_delivery_call_llm"),
        extract_content=context.get("final_delivery_extract_content"),
    )


def evaluate_final_delivery(
    registry: GovernanceRegistry,
    *,
    response_text: str,
    user_text: str = "",
    outcomes: Any = None,
) -> FinalDeliveryDecision:
    review_context = _is_governance_review_context(
        registry,
        user_text=user_text,
        response_text=response_text,
    )
    if _contains_hard_internal_leak(response_text) and not review_context:
        return FinalDeliveryDecision(
            action="block",
            reason="internal_guard_leak",
        )
    if (
        _contains_internal_guard_leak(response_text)
        and not _is_review_quote_context(review_context, response_text)
    ):
        return FinalDeliveryDecision(
            action="block",
            reason="internal_guard_leak",
        )
    if review_context:
        return FinalDeliveryDecision(action="allow", reason="governance_review_context")

    playbook_key = _playbook_key(registry, user_text=user_text, response_text=response_text)
    if not playbook_key:
        return FinalDeliveryDecision(action="allow", reason="no_governed_playbook")
    playbook = registry.get_playbook(playbook_key)
    if _has_review_pass_evidence(
        outcomes if outcomes is not None else (),
        playbook_key=playbook_key,
        required_tools=playbook.required_tools,
    ):
        return FinalDeliveryDecision(
            action="allow",
            reason="review_evidence_passed",
            playbook_key=playbook_key,
        )

    if _is_safe_non_delivery_response(response_text) or not _is_final_delivery_claim(
        registry,
        response_text=response_text,
        playbook_key=playbook_key,
    ):
        return FinalDeliveryDecision(
            action="allow",
            reason="not_final_delivery_claim",
            playbook_key=playbook_key,
        )

    return FinalDeliveryDecision(
        action="block",
        reason="review_evidence_missing",
        playbook_key=playbook_key,
        retry_tools=playbook.required_tools,
    )


def _delivery_evidence(
    decision: FinalDeliveryDecision,
    *,
    context: dict[str, Any],
    outcomes: Any,
) -> dict[str, Any]:
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
        "python_semantic_decision_is_advisory": True,
    }


def _playbook_key(
    registry: GovernanceRegistry,
    *,
    user_text: str,
    response_text: str,
) -> str:
    for text in (user_text, response_text):
        decision = dispatch_request(registry, text)
        if decision.playbook_key:
            return decision.playbook_key
    if (
        _contains_score_delivery_claim(response_text)
        and _has_admission_context(response_text)
        and "susi_score_calculation" in registry.playbooks
    ):
        return "susi_score_calculation"
    return ""


def _is_governance_review_context(
    registry: GovernanceRegistry,
    *,
    user_text: str,
    response_text: str,
) -> bool:
    user_decision = dispatch_request(registry, user_text)
    if user_decision.playbook_key and user_decision.domain not in {"dev", "research"}:
        return False
    user_blob = _normalized_blob(user_text)
    response_blob = _normalized_blob(response_text)
    if not user_blob and not response_blob:
        return False
    has_review_marker = any(
        marker in user_blob or marker in response_blob for marker in _GOVERNANCE_REVIEW_MARKERS
    )
    if not has_review_marker:
        return False
    return not _contains_personalized_delivery_claim(response_text)


def _contains_personalized_delivery_claim(response_text: str) -> bool:
    if _STUDENT_SCORE_CLAIM_RE.search(_normalized_blob(response_text)):
        return True
    blob = _normalized_blob(response_text)
    has_person = any(term in blob for term in _PERSONALIZED_DELIVERY_TERMS)
    if not has_person:
        return False
    if any(marker in blob for marker in _COMPLETION_CLAIM_MARKERS):
        return True
    return any(marker in blob for marker in _DOMAIN_VERDICT_MARKERS)


def _is_final_delivery_claim(
    registry: GovernanceRegistry,
    *,
    response_text: str,
    playbook_key: str,
) -> bool:
    blob = " ".join(str(response_text or "").casefold().split())
    if not blob:
        return False
    if _contains_score_delivery_claim(blob):
        return True
    if _is_meta_system_explanation(blob):
        return False
    if any(marker in blob for marker in _COMPLETION_CLAIM_MARKERS):
        return True
    if not any(marker in blob for marker in _DOMAIN_VERDICT_MARKERS):
        return False
    if any(term in blob for term in _DOMAIN_DELIVERY_TERMS):
        return True
    decision = dispatch_request(registry, response_text)
    return bool(decision.playbook_key and decision.playbook_key == playbook_key)


def _is_meta_system_explanation(blob: str) -> bool:
    if not any(term in blob for term in _META_EXPLANATION_TERMS):
        return False
    if any(term in blob for term in _PERSONALIZED_DELIVERY_TERMS):
        return False
    return not any(term in blob for term in _ARTIFACT_COMPLETION_TERMS)


def _contains_score_delivery_claim(response_text: str) -> bool:
    blob = _normalized_blob(response_text)
    if not blob:
        return False
    return bool(_SCORE_CLAIM_RE.search(blob) or _STUDENT_SCORE_CLAIM_RE.search(blob))


def _contains_internal_guard_leak(response_text: str) -> bool:
    """True if an internal retry/verification instruction leaked into the answer.

    These are concrete guard phrases or governance JSON keys that must never
    reach the user verbatim. Plain user-facing explanations (e.g. "전용 도구가
    필요합니다") do not match because the markers are full instruction clauses.
    """

    return _shared_contains_internal_guard_leak(response_text)


def _is_review_quote_context(review_context: bool, response_text: str) -> bool:
    if not review_context:
        return False
    blob = _normalized_blob(response_text)
    if not any(marker in blob for marker in ("차단 문구", "금지 문구", "인용", "quote")):
        return False
    return any(mark in str(response_text or "") for mark in ("'", '"', "`", "“", "”", "‘", "’"))


def _is_safe_non_delivery_response(response_text: str) -> bool:
    blob = " ".join(str(response_text or "").casefold().split())
    if not blob:
        return True
    if _contains_score_delivery_claim(blob):
        return False
    if any(marker in blob for marker in _COMPLETION_CLAIM_MARKERS):
        return False
    if any(marker in blob for marker in _DOMAIN_VERDICT_MARKERS) and any(
        term in blob for term in _DOMAIN_DELIVERY_TERMS
    ):
        return False
    safe_markers = (
        "?",
        "어느",
        "어떤",
        "누구",
        "알려주세요",
        "보내주세요",
        "필요합니다",
        "필요해요",
        "확인이 필요",
        "원본 대조",
        "진행할 수",
        "확인 중",
        "확인하겠습니다",
        "작업을 시작",
        "계산을 준비",
        "준비하겠습니다",
        "잠시만",
        "기다려 주세요",
        "진행 중",
    )
    return any(marker in blob for marker in safe_markers)


def _has_review_pass_evidence(
    outcomes: Any,
    *,
    playbook_key: str,
    required_tools: tuple[str, ...],
) -> bool:
    required = set(required_tools)
    if not isinstance(outcomes, (list, tuple)):
        return False
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        if str(outcome.get("playbook_key") or "") != playbook_key:
            continue
        if str(outcome.get("review_status") or "") != "pass":
            continue
        if outcome.get("failures"):
            continue
        tools = {str(tool).strip() for tool in outcome.get("tools_used") or []}
        if tools & required:
            return True
    return False


def _outcomes_from_conversation_history(
    registry: GovernanceRegistry,
    messages: Any,
    *,
    user_text: str,
) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    current_turn = messages[_current_turn_start(messages, user_text) :]
    outcomes: list[dict[str, Any]] = []
    for message in current_turn:
        if not isinstance(message, dict) or str(message.get("role") or "") != "tool":
            continue
        tool_name = str(message.get("name") or message.get("tool_name") or "").strip()
        playbook_key = _PLAYBOOK_BY_TOOL.get(tool_name)
        if not playbook_key:
            continue
        payload = _loads_object(message.get("content"))
        if payload is None:
            continue
        review = evaluate_review_gate(
            registry,
            playbook_key=playbook_key,
            tool_name=tool_name,
            result=payload,
            auxiliary_review_policy=auxiliary_review_policy_for_playbook(playbook_key),
        )
        outcomes.append(
            {
                "playbook_key": playbook_key,
                "review_status": review.status,
                "tools_used": [tool_name],
                "failures": _review_failures(review),
            }
        )
    return outcomes


def _current_turn_start(messages: list[Any], user_text: str) -> int:
    fallback = 0
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or str(message.get("role") or "") != "user":
            continue
        fallback = index + 1
        content = _message_text(message.get("content"))
        if user_text and user_text in content:
            return index + 1
    return fallback


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(part for part in parts if part)
    return str(value or "")


def _loads_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    text = _message_text(value)
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _review_failures(review: Any) -> list[str]:
    if getattr(review, "status", "") == "pass":
        return []
    reason = str(getattr(review, "reason", "") or "").strip()
    return [reason] if reason else ["review_not_passed"]
