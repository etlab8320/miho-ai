"""Agentic recovery for blocked final delivery."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from .delivery_safety import contains_internal_guard_leak, contains_non_result_deferral
from .final_qa import repair_answer_until_pass

logger = logging.getLogger(__name__)

BLOCKED_DELIVERY_RECOVERY_TASK = "miho_governance_blocked_delivery_recovery"
BLOCKED_DELIVERY_RECOVERY_TIMEOUT_SECONDS = 20


def recover_blocked_delivery(
    *,
    question: str,
    answer: str,
    evidence: dict[str, Any],
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], str] | None = None,
) -> str | None:
    """Return an LLM-produced replacement for a blocked final answer."""

    original = str(answer or "").strip()
    repaired = repair_answer_until_pass(
        question,
        answer,
        evidence={**evidence, "blocked_delivery_recovery": "final_qa_repair"},
        call_llm=call_llm,
        extract_content=extract_content,
    )
    if _is_usable_replacement(repaired, original):
        return repaired.strip()

    recovered = _request_blocked_recovery(
        question=question,
        answer=answer,
        evidence={**evidence, "blocked_delivery_recovery": "dedicated_agent"},
        call_llm=call_llm,
        extract_content=extract_content,
    )
    if _is_usable_replacement(recovered, original):
        return recovered.strip()
    return _emergency_fail_closed_result(evidence=evidence)


def _request_blocked_recovery(
    *,
    question: str,
    answer: str,
    evidence: dict[str, Any],
    call_llm: Callable[..., Any] | None,
    extract_content: Callable[[Any], str] | None,
) -> str:
    default_call_llm: Callable[..., Any] | None = None
    default_extract: Callable[[Any], str] | None = None
    if call_llm is None or extract_content is None:
        default_call_llm, default_extract = _default_llm_pair()
        call_llm = call_llm or default_call_llm
        extract_content = extract_content or default_extract

    try:
        response = _call_recovery_agent(call_llm, question, answer, evidence=evidence)
    except Exception as exc:
        logger.info("governance blocked delivery recovery skipped: %s", exc)
        if default_call_llm is None or default_extract is None:
            default_call_llm, default_extract = _default_llm_pair()
        if call_llm is default_call_llm:
            return ""
        try:
            response = _call_recovery_agent(
                default_call_llm,
                question,
                answer,
                evidence={**evidence, "recovery_transport_fallback": True},
            )
            extract_content = default_extract
        except Exception as fallback_exc:
            logger.info("governance blocked delivery default recovery skipped: %s", fallback_exc)
            return ""
    return str(extract_content(response) or "").strip()


def _default_llm_pair() -> tuple[Callable[..., Any], Callable[[Any], str]]:
    from agent.auxiliary_client import call_llm as default_call_llm
    from agent.auxiliary_client import extract_content_or_reasoning

    return default_call_llm, extract_content_or_reasoning


def _call_recovery_agent(
    call_llm: Callable[..., Any],
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any],
) -> Any:
    return call_llm(
        task=BLOCKED_DELIVERY_RECOVERY_TASK,
        messages=blocked_recovery_messages(question, answer, evidence=evidence),
        temperature=0.0,
        max_tokens=900,
        timeout=BLOCKED_DELIVERY_RECOVERY_TIMEOUT_SECONDS,
    )


def blocked_recovery_messages(
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "너는 미호의 Blocked Delivery Recovery Agent다. fallback 문구가 아니라 "
                "사용자에게 보낼 최종 답변 본문을 직접 작성한다. 사용자 질문 Q, 차단된 답변 A, "
                "evidence JSON을 보고 Q에 맞는 한국어 평문 답변만 출력한다. 내부 guard, "
                "retry_tools, provider 오류, stack trace, 검증 실패 안내를 노출하지 않는다. "
                "evidence가 부족한 도메인 산출물의 완료/첨부/점수 claim은 확정하지 않는다. "
                "확인한 뒤 전달, 검증 후 전달, 준비하겠습니다 같은 대기 문구는 답변이 아니다. "
                "Q가 거버넌스/셀프하네스/코드 리뷰라면 리뷰 결과를 유지하고, 산출물 전달로 오해하지 않는다."
            ),
        },
        {
            "role": "user",
            "content": "Q: "
            + str(question or "")
            + "\nA: "
            + str(answer or "")
            + "\nEVIDENCE: "
            + json.dumps(evidence or {}, ensure_ascii=False, sort_keys=True),
        },
    ]


def _is_usable_replacement(candidate: str, original: str) -> bool:
    replacement = str(candidate or "").strip()
    return bool(
        replacement
        and replacement != original
        and not contains_internal_guard_leak(replacement)
        and not contains_non_result_deferral(replacement)
    )


def _emergency_fail_closed_result(*, evidence: dict[str, Any]) -> str:
    """Last resort when every LLM recovery path is unavailable.

    This is not a semantic/domain fallback. It only prevents a blocked original
    claim from failing open when every agent transport is unavailable.
    """

    _record_recovery_transport_failure(evidence)
    decision = evidence.get("decision") if isinstance(evidence, dict) else {}
    retry_tools = decision.get("retry_tools") if isinstance(decision, dict) else []
    if isinstance(retry_tools, list) and retry_tools:
        return "현재 결론: 확정 산출물 없음.\n필요한 입력: 원자료 또는 생성된 산출물."
    if retry_tools:
        return "현재 결론: 확정 산출물 없음.\n필요한 입력: 원자료 또는 생성된 산출물."
    return "현재 결론: 확정 산출물 없음.\n필요한 입력: 요청을 판단할 원자료."


def _record_recovery_transport_failure(evidence: dict[str, Any]) -> None:
    try:
        from .feedback_events import record_quality_failure

        decision = evidence.get("decision") if isinstance(evidence, dict) else {}
        if not isinstance(decision, dict):
            decision = {}
        retry_tools = decision.get("retry_tools")
        tools_used = tuple(str(tool) for tool in retry_tools) if isinstance(retry_tools, list) else ()
        record_quality_failure(
            request_id=str(evidence.get("session_id") or "final_delivery_recovery"),
            playbook_key=str(decision.get("playbook_key") or "unknown"),
            failure_signature="final_delivery_recovery_transport_unavailable",
            user_feedback="Final Delivery recovery agents were unavailable in a blocked delivery path.",
            tools_used=tools_used,
        )
    except Exception as exc:
        logger.debug("failed to record final delivery recovery transport failure: %s", exc)
