"""LLM semantic judge for Governance OS final delivery decisions."""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from .delivery_safety import contains_internal_guard_leak

logger = logging.getLogger(__name__)

SEMANTIC_DELIVERY_JUDGE_TASK = "miho_governance_semantic_delivery_judge"
SEMANTIC_DELIVERY_TIMEOUT_SECONDS = 20
SemanticAction = Literal["allow", "block", "abstain"]


@dataclass(frozen=True)
class SemanticDeliveryVerdict:
    action: SemanticAction
    reason: str
    playbook_key: str = ""
    retry_tools: tuple[str, ...] = field(default_factory=tuple)


def judge_delivery_semantics(
    *,
    question: str,
    answer: str,
    evidence: dict[str, Any],
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], str] | None = None,
) -> SemanticDeliveryVerdict | None:
    """Ask an LLM agent whether advisory Python delivery hints are right."""

    if not str(question or "").strip() or not str(answer or "").strip():
        return None
    if contains_internal_guard_leak(answer):
        return None
    try:
        payload = _request_semantic_verdict(
            question=question,
            answer=answer,
            evidence=evidence,
            call_llm=call_llm,
            extract_content=extract_content,
        )
    except Exception as exc:
        logger.info("governance semantic delivery judge skipped: %s", exc)
        return None
    return _verdict_from_payload(payload)


def semantic_judge_messages(
    question: str,
    answer: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "너는 미호의 Semantic Delivery Judge다. runtime이 제공한 후보 feature와 "
                "evidence는 참고 신호일 뿐이고, 최종 의미판단은 네가 한다. "
                "사용자 질문 Q와 답변 후보 A, "
                "evidence JSON을 보고 A가 실제 도메인 산출물/점수/첨부 완료 claim인지, "
                "아니면 거버넌스/코드/시스템 리뷰나 일반 설명인지 판단한다. "
                "반드시 JSON만 출력한다: "
                "{\"action\":\"allow|block|abstain\",\"reason\":\"...\","
                "\"playbook_key\":\"...\",\"retry_tools\":[\"...\"]}. "
                "allow는 Python advisory block이 오탐이라고 판단할 때만 쓴다. "
                "block은 도구/reviewer 근거 없이 실제 산출물, 계산, 추천, 첨부 완료를 "
                "말한다고 판단할 때 쓴다. abstain은 확신이 없거나 물리적 안전/내부 문구 "
                "판단이면 쓴다. 확인 후 전달/검증 뒤 전달/자료 보내주면 처리 같은 "
                "비결과 답변도 단어/정규식 규칙이 아니라 네가 Q와 evidence를 보고 "
                "현재 턴의 최종 결과인지 직접 판단한다. 거버넌스/셀프하네스/미호 시스템 적대적 리뷰 요청은 "
                "수시/학종/PDF/점수 단어가 있어도 실제 학생 산출물로 오해하지 마라."
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


def _request_semantic_verdict(
    *,
    question: str,
    answer: str,
    evidence: dict[str, Any],
    call_llm: Callable[..., Any] | None,
    extract_content: Callable[[Any], str] | None,
) -> dict[str, Any] | None:
    if call_llm is None or extract_content is None:
        if _running_under_pytest():
            return None
        from agent.auxiliary_client import call_llm as default_call_llm
        from agent.auxiliary_client import extract_content_or_reasoning

        call_llm = call_llm or default_call_llm
        extract_content = extract_content or extract_content_or_reasoning

    response = call_llm(
        task=SEMANTIC_DELIVERY_JUDGE_TASK,
        messages=semantic_judge_messages(question, answer, evidence=evidence),
        temperature=0.0,
        max_tokens=700,
        timeout=SEMANTIC_DELIVERY_TIMEOUT_SECONDS,
    )
    parsed = _parse_json_payload(str(extract_content(response) or ""))
    return parsed if isinstance(parsed, dict) else None


def _verdict_from_payload(payload: dict[str, Any] | None) -> SemanticDeliveryVerdict | None:
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action") or "").strip().casefold()
    if action not in {"allow", "block", "abstain"}:
        return None
    reason = str(payload.get("reason") or "agent_semantic_verdict").strip()
    playbook_key = str(payload.get("playbook_key") or "").strip()
    retry_tools = tuple(
        str(tool).strip()
        for tool in payload.get("retry_tools") or []
        if str(tool).strip()
    )
    return SemanticDeliveryVerdict(
        action=cast(SemanticAction, action),
        reason=reason,
        playbook_key=playbook_key,
        retry_tools=retry_tools,
    )


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
        start = body.find("{")
        end = body.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(body[start : end + 1])


def _running_under_pytest() -> bool:
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))
