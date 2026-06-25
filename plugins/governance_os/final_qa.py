"""LLM final QA agent for Governance OS user-facing answers."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any


logger = logging.getLogger(__name__)
FINAL_QA_TASK = "miho_governance_final_qa"
FINAL_QA_REPAIR_TASK = "miho_governance_final_qa_repair"
FINAL_QA_TIMEOUT_SECONDS = 8
FINAL_QA_REPAIR_TIMEOUT_SECONDS = 20
FINAL_QA_REPAIR_ATTEMPTS = 2
PASS_VERDICT = "pass"
REVISE_VERDICT = "revise"
SAFE_REPAIR_FALLBACK = (
    "방금 답변은 확인 근거가 충분하지 않아 그대로 전달하지 않겠습니다. "
    "필요한 확인을 다시 거쳐 이어서 답하겠습니다."
)


async def verdict_or_pass(
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> str:
    """Return LLM final QA verdict for a proposed user-facing answer.

    The judgement is intentionally delegated to the auxiliary LLM. Python only
    routes the verdict. If the reviewer transport fails, keep the answer rather
    than surfacing an internal validation failure to the user.
    """
    if not str(question or "").strip() or not str(answer or "").strip():
        return PASS_VERDICT
    try:
        raw = await asyncio.wait_for(
            _request_verdict(question, answer, evidence=evidence or {}),
            FINAL_QA_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.info("governance final QA skipped: %s", exc)
        return PASS_VERDICT
    return PASS_VERDICT if _is_pass(raw) else REVISE_VERDICT


async def _request_verdict(
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any],
) -> str:
    from agent.auxiliary_client import async_call_llm, extract_content_or_reasoning

    response = await async_call_llm(
        task=FINAL_QA_TASK,
        messages=verdict_messages(question, answer, evidence=evidence),
        temperature=0.0,
        max_tokens=12,
        timeout=FINAL_QA_TIMEOUT_SECONDS,
    )
    return str(extract_content_or_reasoning(response) or "").strip()


def verdict_messages(
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "너는 미호의 Final QA Agent다. 사용자 질문 Q, 최종 답변 후보 A, "
                "도구/리뷰 evidence를 보고 사용자에게 보내도 되는지 판단한다. "
                "A가 Q에 맞고, 내부 오류/guard/retry 지시를 사용자에게 노출하지 않고, "
                "도구 검증 증거와 모순되지 않으면 정확히 'pass' 한 단어만 출력해라. "
                "질문에 빗나갔거나, 내부 검증/재시도 지시를 최종 답변처럼 말하거나, "
                "완료/첨부/검증 주장과 evidence가 맞지 않으면 정확히 'revise' 한 단어만 출력해라. "
                "설명은 절대 붙이지 마라."
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


def repair_answer_or_original(
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any] | None = None,
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], str] | None = None,
) -> str:
    """Ask an LLM repair agent for a replacement answer, keeping nonempty fallback."""

    if not str(question or "").strip() or not str(answer or "").strip():
        return str(answer or "")
    try:
        raw = _request_repair(
            question,
            answer,
            evidence=evidence or {},
            call_llm=call_llm,
            extract_content=extract_content,
        )
    except Exception as exc:
        logger.info("governance final QA repair skipped: %s", exc)
        return str(answer or "")
    repaired = str(raw or "").strip()
    return repaired or str(answer or "")


def repair_answer_until_pass(
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any] | None = None,
    max_attempts: int = FINAL_QA_REPAIR_ATTEMPTS,
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], str] | None = None,
) -> str:
    """Run LLM repair and LLM final QA until the candidate passes."""

    if not str(question or "").strip() or not str(answer or "").strip():
        return str(answer or "")

    candidate = str(answer or "")
    current_evidence = dict(evidence or {})
    attempts = max(1, int(max_attempts or 1))
    for attempt in range(1, attempts + 1):
        repaired = repair_answer_or_original(
            question,
            candidate,
            evidence=current_evidence,
            call_llm=call_llm,
            extract_content=extract_content,
        ).strip()
        if repaired:
            candidate = repaired
        verdict = _verdict_or_revise_sync(
            question,
            candidate,
            evidence={**current_evidence, "repair_attempt": attempt},
            call_llm=call_llm,
            extract_content=extract_content,
        )
        if verdict == PASS_VERDICT:
            return candidate
        current_evidence = {
            **current_evidence,
            "previous_final_qa_verdict": verdict,
            "repair_attempt": attempt,
        }
    return SAFE_REPAIR_FALLBACK


def _request_repair(
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any],
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], str] | None = None,
) -> str:
    if call_llm is None or extract_content is None:
        from agent.auxiliary_client import call_llm as default_call_llm
        from agent.auxiliary_client import extract_content_or_reasoning

        call_llm = call_llm or default_call_llm
        extract_content = extract_content or extract_content_or_reasoning

    response = call_llm(
        task=FINAL_QA_REPAIR_TASK,
        messages=repair_messages(question, answer, evidence=evidence),
        temperature=0.0,
        max_tokens=700,
        timeout=FINAL_QA_REPAIR_TIMEOUT_SECONDS,
    )
    return str(extract_content(response) or "").strip()


def _verdict_or_revise_sync(
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any],
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], str] | None = None,
) -> str:
    if call_llm is None or extract_content is None:
        from agent.auxiliary_client import call_llm as default_call_llm
        from agent.auxiliary_client import extract_content_or_reasoning

        call_llm = call_llm or default_call_llm
        extract_content = extract_content or extract_content_or_reasoning

    try:
        response = call_llm(
            task=FINAL_QA_TASK,
            messages=verdict_messages(question, answer, evidence=evidence),
            temperature=0.0,
            max_tokens=12,
            timeout=FINAL_QA_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.info("governance final QA sync check skipped: %s", exc)
        return REVISE_VERDICT
    raw = str(extract_content(response) or "").strip()
    return PASS_VERDICT if _is_pass(raw) else REVISE_VERDICT


def repair_messages(
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "너는 미호의 Final QA Repair Agent다. 사용자 질문 Q, 문제 있는 최종 답변 후보 A, "
                "도구/리뷰 evidence를 보고 사용자가 바로 받을 새 최종 답변만 작성한다. "
                "내부 guard, retry_tools, stack trace, provider 오류, 검증 실패 문구를 노출하지 마라. "
                "도구 evidence가 부족하면 완료/첨부/점수/검증을 확정하지 말고, "
                "사용자의 질문에 맞는 다음 응답을 한국어 평문으로 작성한다. "
                "설명 없이 새 최종 답변 본문만 출력해라."
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


def _is_revise(verdict: str) -> bool:
    return str(verdict or "").strip().casefold() == REVISE_VERDICT


def _is_pass(verdict: str) -> bool:
    return str(verdict or "").strip().casefold() == PASS_VERDICT
