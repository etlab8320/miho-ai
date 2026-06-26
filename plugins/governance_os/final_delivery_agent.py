"""LLM Final Delivery Agent for Governance OS user-facing answers."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from .delivery_safety import contains_internal_guard_leak, contains_non_result_deferral

logger = logging.getLogger(__name__)

FINAL_DELIVERY_TASK = "miho_governance_final_delivery"
FINAL_DELIVERY_TIMEOUT_SECONDS = 30


def review_final_delivery(
    *,
    question: str,
    answer: str,
    evidence: dict[str, Any],
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], str] | None = None,
) -> str | None:
    """Ask the LLM Final Delivery Agent for the user-facing final answer.

    Python only packages evidence and validates the agent's structured answer.
    It does not generate user-facing fallback prose.
    """

    if not str(question or "").strip() or not str(answer or "").strip():
        return None
    try:
        payload = _request_final_delivery(
            question=question,
            answer=answer,
            evidence=evidence,
            call_llm=call_llm,
            extract_content=extract_content,
        )
    except Exception as exc:
        logger.info("governance final delivery agent skipped: %s", exc)
        return None
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action") or "").strip().casefold()
    candidate = str(payload.get("answer") or "").strip()
    if action not in {"deliver", "revise", "block"} or not candidate:
        return None
    if contains_internal_guard_leak(candidate) or contains_non_result_deferral(candidate):
        return None
    original = str(answer or "").strip()
    if candidate == original and _requires_agent_verdict(evidence):
        return candidate
    return candidate if candidate != original else None


def _requires_agent_verdict(evidence: dict[str, Any]) -> bool:
    if not isinstance(evidence, dict):
        return False
    return bool(evidence.get("require_agent_verdict"))


def _request_final_delivery(
    *,
    question: str,
    answer: str,
    evidence: dict[str, Any],
    call_llm: Callable[..., Any] | None,
    extract_content: Callable[[Any], str] | None,
) -> dict[str, Any] | None:
    if call_llm is None or extract_content is None:
        from agent.auxiliary_client import call_llm as default_call_llm
        from agent.auxiliary_client import extract_content_or_reasoning

        call_llm = call_llm or default_call_llm
        extract_content = extract_content or extract_content_or_reasoning

    response = call_llm(
        task=FINAL_DELIVERY_TASK,
        messages=final_delivery_messages(question, answer, evidence=evidence),
        temperature=0.0,
        max_tokens=1400,
        timeout=FINAL_DELIVERY_TIMEOUT_SECONDS,
    )
    parsed = _parse_json_payload(str(extract_content(response) or ""))
    return parsed if isinstance(parsed, dict) else None


def final_delivery_messages(
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "너는 미호의 Final Delivery Agent다. Python guard가 아니라 LLM 최종 전달자다. "
                "사용자 질문 Q와 최종 답변 후보 A, evidence JSON만 보고 사용자에게 보낼 최종 본문을 결정한다. "
                "반드시 JSON만 출력한다: {\"action\":\"deliver|revise|block\",\"answer\":\"...\"}. "
                "Q가 거버넌스/셀프하네스/코드/시스템 적대적 리뷰 요청이면, A 안의 수시/학종/점수/첨부 같은 단어를 "
                "실제 학원 산출물 전달로 오해하지 말고 리뷰 결과를 유지한다. "
                "내부 guard, retry_tools, stack trace, provider 오류, 검증 실패 안내를 사용자 답변으로 노출하지 않는다. "
                "도메인 산출물의 완료/첨부/점수 claim이 evidence와 맞지 않으면 revise로 고쳐라. "
                "확인한 뒤 전달, 검증 후 전달, 준비하겠습니다 같은 대기 문구는 답변이 아니다. "
                "답변을 고칠 때도 Q에 직접 답하고, 현재 정보로 가능한 결론이나 필요한 입력을 말해라."
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


def _parse_json_payload(text: str) -> Any:
    body = str(text or "").strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines).strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start_points = [index for index in (body.find("{"), body.find("[")) if index >= 0]
        if not start_points:
            raise
        start = min(start_points)
        end = max(body.rfind("}"), body.rfind("]"))
        if end <= start:
            raise
        return json.loads(body[start : end + 1])
