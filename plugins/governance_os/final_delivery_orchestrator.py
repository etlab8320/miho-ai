"""LLM tool-planning layer for Final Delivery recovery."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from plugins.decision_twin.contracts import decision_tool_contracts

from .delivery_safety import contains_internal_guard_leak, contains_non_result_deferral

logger = logging.getLogger(__name__)

FINAL_DELIVERY_ORCHESTRATOR_TASK = "miho_governance_final_delivery_orchestrator"
FINAL_DELIVERY_ORCHESTRATOR_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class FinalDeliveryToolStep:
    tool_name: str
    args: dict[str, Any]


def plan_final_delivery_retry(
    *,
    question: str,
    answer: str,
    playbook_key: str,
    retry_tools: tuple[str, ...],
    conversation_history: Any,
    evidence: dict[str, Any],
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], str] | None = None,
) -> tuple[FinalDeliveryToolStep, ...]:
    """Ask the LLM Final Delivery Orchestrator for executable tool steps."""

    allowed_tools = tuple(str(tool).strip() for tool in retry_tools if str(tool).strip())
    if not allowed_tools:
        return ()
    try:
        payload = _request_orchestrator_payload(
            mode="plan_tools",
            question=question,
            answer=answer,
            playbook_key=playbook_key,
            allowed_tools=allowed_tools,
            conversation_history=conversation_history,
            evidence=evidence,
            verified_tool_results=(),
            call_llm=call_llm,
            extract_content=extract_content,
        )
    except Exception as exc:
        logger.info("final delivery orchestrator skipped: %s", exc)
        return ()
    return _steps_from_payload(payload, allowed_tools=set(allowed_tools))


def compose_final_delivery_answer(
    *,
    question: str,
    answer: str,
    playbook_key: str,
    retry_tools: tuple[str, ...],
    conversation_history: Any,
    evidence: dict[str, Any],
    verified_tool_results: tuple[dict[str, Any], ...],
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], str] | None = None,
) -> str | None:
    """Ask the LLM orchestrator to write the final answer from verified results."""

    allowed_tools = tuple(str(tool).strip() for tool in retry_tools if str(tool).strip())
    if not verified_tool_results:
        return None
    try:
        payload = _request_orchestrator_payload(
            mode="compose_answer",
            question=question,
            answer=answer,
            playbook_key=playbook_key,
            allowed_tools=allowed_tools,
            conversation_history=conversation_history,
            evidence=evidence,
            verified_tool_results=verified_tool_results,
            call_llm=call_llm,
            extract_content=extract_content,
        )
    except Exception as exc:
        logger.info("final delivery orchestrator compose skipped: %s", exc)
        return None
    return _answer_from_payload(payload)


def _request_orchestrator_payload(
    *,
    mode: str,
    question: str,
    answer: str,
    playbook_key: str,
    allowed_tools: tuple[str, ...],
    conversation_history: Any,
    evidence: dict[str, Any],
    verified_tool_results: tuple[dict[str, Any], ...],
    call_llm: Callable[..., Any] | None,
    extract_content: Callable[[Any], str] | None,
) -> dict[str, Any] | None:
    if call_llm is None or extract_content is None:
        from agent.auxiliary_client import call_llm as default_call_llm
        from agent.auxiliary_client import extract_content_or_reasoning

        call_llm = call_llm or default_call_llm
        extract_content = extract_content or extract_content_or_reasoning

    response = call_llm(
        task=FINAL_DELIVERY_ORCHESTRATOR_TASK,
        messages=final_delivery_orchestrator_messages(
            mode=mode,
            question=question,
            answer=answer,
            playbook_key=playbook_key,
            allowed_tools=allowed_tools,
            conversation_history=conversation_history,
            evidence=evidence,
            verified_tool_results=verified_tool_results,
        ),
        temperature=0,
        max_tokens=1600,
        timeout=FINAL_DELIVERY_ORCHESTRATOR_TIMEOUT_SECONDS,
    )
    parsed = _parse_json_payload(str(extract_content(response) or ""))
    return parsed if isinstance(parsed, dict) else None


def final_delivery_orchestrator_messages(
    *,
    mode: str,
    question: str,
    answer: str,
    playbook_key: str,
    allowed_tools: tuple[str, ...],
    conversation_history: Any,
    evidence: dict[str, Any] | None = None,
    verified_tool_results: tuple[dict[str, Any], ...] = (),
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "너는 미호의 Final Delivery Orchestrator다. Python fallback 문구가 아니라 "
                "LLM agent로 최종 전달을 완성한다. "
                "mode=plan_tools이면 현재 턴 안에서 실행할 도구 계획만 JSON으로 반환한다. "
                "mode=compose_answer이면 verified_tool_results와 evidence만 근거로 "
                "사용자에게 보낼 최종 답변을 JSON으로 반환한다. "
                "도구 계획은 반드시 허용된 allowed_tools 안에서만 steps를 만든다. "
                "사용자 질문, 대화 기록, tool_contracts, evidence를 보고 필요한 입력을 추론하되 "
                "없는 사실을 꾸며내지 않는다. "
                "plan_tools 반환 형식: {\"action\":\"run_tools|needs_input\",\"steps\":[{\"tool_name\":\"...\",\"args\":{...}}],\"reason\":\"...\"}. "
                "compose_answer 반환 형식: {\"action\":\"deliver|revise|needs_input\",\"answer\":\"...\",\"reason\":\"...\"}. "
                "실행 가능한 계획이면 action=run_tools, 필요한 입력이 실제로 없으면 needs_input이다. "
                "retry/fallback/guard/provider/후검증 같은 내부 용어를 사용자 답변으로 만들지 않는다."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "mode": mode,
                    "question": question,
                    "answer_candidate": answer,
                    "playbook_key": playbook_key,
                    "allowed_tools": list(allowed_tools),
                    "tool_contracts": _tool_contract_subset(allowed_tools),
                    "conversation_history": _compact_history(conversation_history),
                    "evidence": evidence or {},
                    "verified_tool_results": list(verified_tool_results),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def _steps_from_payload(
    payload: dict[str, Any] | None,
    *,
    allowed_tools: set[str],
) -> tuple[FinalDeliveryToolStep, ...]:
    if not isinstance(payload, dict):
        return ()
    if str(payload.get("action") or "").strip() != "run_tools":
        return ()
    steps: list[FinalDeliveryToolStep] = []
    for item in payload.get("steps") or []:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or "").strip()
        args = item.get("args")
        if tool_name in allowed_tools and isinstance(args, dict):
            steps.append(FinalDeliveryToolStep(tool_name=tool_name, args=dict(args)))
    return tuple(steps)


def _answer_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    if str(payload.get("action") or "").strip() not in {"deliver", "revise", "needs_input"}:
        return None
    candidate = str(payload.get("answer") or "").strip()
    if not candidate:
        return None
    if contains_internal_guard_leak(candidate) or contains_non_result_deferral(candidate):
        return None
    return candidate


def _tool_contract_subset(tool_names: tuple[str, ...]) -> dict[str, Any]:
    contracts = decision_tool_contracts()
    return {name: contracts.get(name, {}) for name in tool_names}


def _compact_history(history: Any) -> list[dict[str, Any]]:
    if not isinstance(history, list):
        return []
    compact: list[dict[str, Any]] = []
    for message in history[-8:]:
        if not isinstance(message, dict):
            continue
        item: dict[str, Any] = {
            "role": str(message.get("role") or ""),
            "name": str(message.get("name") or message.get("tool_name") or ""),
        }
        content = message.get("content")
        if content is not None:
            item["content"] = str(content)[:3000]
        if message.get("tool_calls"):
            item["tool_calls"] = message.get("tool_calls")
        compact.append(item)
    return compact


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
