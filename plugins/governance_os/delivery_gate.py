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
    GOVERNANCE_JSON_LEAK_KEYS as _GOVERNANCE_JSON_LEAK_KEYS,
    GOVERNANCE_JSON_LEAK_PAIRS as _GOVERNANCE_JSON_LEAK_PAIRS,
    GOVERNANCE_REVIEW_MARKERS as _GOVERNANCE_REVIEW_MARKERS,
    INTERNAL_GUARD_LEAK_MARKERS as _INTERNAL_GUARD_LEAK_MARKERS,
    META_EXPLANATION_TERMS as _META_EXPLANATION_TERMS,
    PERSONALIZED_DELIVERY_TERMS as _PERSONALIZED_DELIVERY_TERMS,
    PLAYBOOK_BY_TOOL as _PLAYBOOK_BY_TOOL,
    SCORE_CLAIM_RE as _SCORE_CLAIM_RE,
    STUDENT_SCORE_CLAIM_RE as _STUDENT_SCORE_CLAIM_RE,
)
from .dispatcher import dispatch_request
from .final_qa_runtime import repair_blocked_answer
from .registry import GovernanceRegistry
from .review import auxiliary_review_policy_for_playbook, evaluate_review_gate
from .versioning import load_runtime_registry


FinalDeliveryAction = Literal["allow", "block"]

_MEDIA_TAG_RE = re.compile(
    r"MEDIA:\s*(?:`([^`\n]+)`|\"([^\"\n]+)\"|'([^'\n]+)'|((?:~/|/)[^\s`\"']+))"
)

# Invisible / bidi-control characters that could split a guard or score marker
# (e.g. "후​검증") and slip past substring detection. Stripped before matching.
_INVISIBLE_RE = re.compile(r"[​‌‍‎‏‪-‮⁠﻿]")


def _normalized_blob(text: Any) -> str:
    """Casefold + collapse whitespace + strip invisible/bidi chars for matching."""

    return " ".join(_INVISIBLE_RE.sub("", str(text or "")).casefold().split())


_ATTACHMENT_UNAVAILABLE_NOTE = "(첨부 파일을 확인할 수 없어 링크를 제외했습니다)"

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

    # Final Delivery Gate also owns attachment-path correction: stage real local
    # artifacts into the safe media cache and rewrite the MEDIA tag in place.
    attachment_fixed = _repair_attachment_paths(original_text)
    effective_text = attachment_fixed if attachment_fixed is not None else original_text

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
    if decision.action != "block":
        # Return the attachment-corrected text when we changed it; otherwise leave unchanged.
        return attachment_fixed
    repaired = repair_blocked_answer(
        user_text=user_text,
        response_text=effective_text,
        decision=decision,
        context=context,
    )
    if repaired:
        return repaired
    return decision.message_ko


def _repair_attachment_paths(response_text: str) -> str | None:
    """Stage real local artifacts referenced by MEDIA tags into the safe cache.

    Returns the rewritten text if any attachment path was corrected, else None.
    Only ``repaired`` outcomes (path actually moved) trigger a rewrite; already
    deliverable paths and un-stageable ones are left untouched.
    """

    text = str(response_text or "")
    if "MEDIA:" not in text:
        return None
    matches = list(_MEDIA_TAG_RE.finditer(text))
    if not matches:
        return None

    from .final_delivery_repair import repair_artifact_delivery

    replacements: list[tuple[str, str]] = []
    for match in matches:
        raw_path = next((group for group in match.groups() if group), "").strip()
        if not raw_path:
            continue
        try:
            repair = repair_artifact_delivery(raw_path)
        except Exception:
            # On a repair error we cannot trust the path: drop the broken tag
            # rather than ship an undeliverable attachment to the user.
            replacements.append((match.group(0), _ATTACHMENT_UNAVAILABLE_NOTE))
            continue
        if (
            repair.status == "repaired"
            and repair.artifact_path
            and repair.artifact_path != raw_path
        ):
            replacements.append((match.group(0), f"MEDIA:`{repair.artifact_path}`"))
        elif repair.status == "blocked":
            # Path is missing / unsafe / un-stageable — never leak a dead MEDIA tag.
            replacements.append((match.group(0), _ATTACHMENT_UNAVAILABLE_NOTE))

    if not replacements:
        return None
    result = text
    for old, new in replacements:
        result = result.replace(old, new, 1)
    return result


def evaluate_final_delivery(
    registry: GovernanceRegistry,
    *,
    response_text: str,
    user_text: str = "",
    outcomes: Any = None,
) -> FinalDeliveryDecision:
    if _is_governance_review_context(registry, user_text=user_text, response_text=response_text):
        return FinalDeliveryDecision(action="allow", reason="governance_review_context")

    if _contains_internal_guard_leak(response_text):
        return FinalDeliveryDecision(
            action="block",
            reason="internal_guard_leak",
            message_ko=(
                "방금 답변에 내부 점검 안내가 섞여 그대로 전달하지 않겠습니다. "
                "질문에 맞춰 다시 정리해 답하겠습니다."
            ),
        )

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
        message_ko=(
            "방금 답변은 확인 근거가 충분하지 않아 그대로 전달하지 않겠습니다. "
            "필요한 확인을 다시 거쳐 이어서 답하겠습니다."
        ),
        retry_tools=playbook.required_tools,
    )


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
    if _contains_concrete_governed_delivery_claim(registry, response_text):
        return False
    blob = " ".join(f"{user_text}\n{response_text}".casefold().split())
    if not blob:
        return False
    return any(marker in blob for marker in _GOVERNANCE_REVIEW_MARKERS)


def _contains_concrete_governed_delivery_claim(
    registry: GovernanceRegistry,
    response_text: str,
) -> bool:
    blob = " ".join(str(response_text or "").casefold().split())
    if not blob:
        return False
    if _contains_score_delivery_claim(blob):
        return True
    decision = dispatch_request(registry, response_text)
    if not decision.playbook_key or decision.domain in {"dev", "research"}:
        return False
    return _is_final_delivery_claim(
        registry,
        response_text=response_text,
        playbook_key=decision.playbook_key,
    )


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

    blob = _normalized_blob(response_text)
    if not blob:
        return False
    if any(marker.casefold() in blob for marker in _INTERNAL_GUARD_LEAK_MARKERS):
        return True
    if any(key.casefold() in blob for key in _GOVERNANCE_JSON_LEAK_KEYS):
        return True
    return any(
        left.casefold() in blob and right.casefold() in blob
        for left, right in _GOVERNANCE_JSON_LEAK_PAIRS
    )


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
