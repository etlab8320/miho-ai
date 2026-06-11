"""LLM decision router for Miho gateway turns."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .contracts import decision_tool_contracts


logger = logging.getLogger(__name__)
DecisionResolver = Callable[[list[dict[str, str]]], Awaitable[Any]]
DECISION_TWIN_TASK = "miho_decision_twin"
MIN_ROUTE_CONFIDENCE = 0.72


@dataclass(frozen=True)
class LlmRouteDecision:
    action: str = "allow"
    route: str = ""
    intent: str = ""
    required_tool: str = ""
    confidence: float = 0.0
    evidence: tuple[str, ...] = field(default_factory=tuple)
    tool_instruction: str = ""
    user_message: str = ""


async def default_decision_resolver(messages: list[dict[str, str]]) -> Any:
    from agent.auxiliary_client import async_call_llm

    return await async_call_llm(
        task=DECISION_TWIN_TASK,
        messages=messages,
        temperature=0,
        max_tokens=420,
        timeout=18,
        extra_body={"reasoning": {"effort": "low"}},
    )


def build_decision_messages(
    *,
    user_text: str,
    owner_context: str = "",
    turn_context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    payload = {
        "user_text": user_text,
        "turn_context": turn_context or {},
        "owner_memory": owner_context,
        "tool_contracts": decision_tool_contracts(),
        "return_schema": {
            "action": "route|allow|clarify",
            "route": "decision_twin|life_record|academy_ops|youtube_ops|gateway_media|conversation",
            "intent": "semantic user job",
            "required_tool": "tool name when a tool/contract must be used",
            "confidence": "0.0-1.0",
            "evidence": ["short reasons from text/context/memory"],
            "tool_instruction": "one concrete instruction for the body agent",
            "user_message": "Korean plain-language clarification only when action=clarify",
        },
    }
    return [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def parse_decision_payload(value: Any) -> LlmRouteDecision:
    payload = _coerce_payload(value)
    if not isinstance(payload, dict):
        return LlmRouteDecision()
    return LlmRouteDecision(
        action=_clean_token(payload.get("action"), default="allow"),
        route=_clean_token(payload.get("route")),
        intent=str(payload.get("intent") or "").strip(),
        required_tool=_clean_token(payload.get("required_tool")),
        confidence=_confidence(payload.get("confidence")),
        evidence=_evidence(payload.get("evidence")),
        tool_instruction=str(payload.get("tool_instruction") or "").strip(),
        user_message=str(payload.get("user_message") or "").strip(),
    )


def should_route_decision(decision: LlmRouteDecision) -> bool:
    if decision.action not in {"route", "execute", "rewrite"}:
        return False
    if not decision.required_tool:
        return False
    return decision.confidence >= MIN_ROUTE_CONFIDENCE


def route_result_text(user_text: str, decision: LlmRouteDecision) -> str:
    instruction = decision.tool_instruction or "사용자 요청을 처리한다."
    evidence = ", ".join(decision.evidence) if decision.evidence else "LLM decision twin"
    return (
        "[Miho decision twin]\n"
        f"의도: {decision.intent or decision.required_tool}\n"
        f"근거: {evidence}\n"
        f"반드시 `{decision.required_tool}` 도구 또는 해당 플러그인 계약을 사용해라.\n"
        f"도구 지시: {instruction}\n"
        "도구 실행 전후로 원문 근거가 부족하면 일반 답변으로 때우지 말고 필요한 파일/로그인/학생명을 요청해라.\n"
        f"사용자 원문: {user_text}"
    )


def _system_prompt() -> str:
    return (
        "너는 Miho 게이트웨이 앞단의 LLM decision twin이다. 사용자에게 직접 답하지 말고 JSON만 반환해. "
        "키워드 하나로 라우팅하지 말고 현재 문장, 첨부, reply/thread context, owner_memory, tool_contracts를 함께 읽어라. "
        "사용자의 실제 job을 추론하고, 전용 도구나 MEDIA 계약이 필요한 경우 action=route와 required_tool을 채워라. "
        "생기부/학종/학원DB/유튜브/파일전달처럼 근거 도구가 필요한 업무는 기억이나 추측만으로 답하게 두지 마라. "
        "확신이 낮거나 필수 인자가 없으면 action=allow 또는 clarify로 둔다. "
        "clarify의 user_message는 한국어 평문이어야 하고 400/401/CORS/stack trace 같은 개발자 표현을 쓰지 마라. "
        "도구 계약에 없는 도구명을 만들지 말고, required_tool은 tool_contracts의 키 중 하나만 사용해라."
    )


def _coerce_payload(value: Any) -> Any:
    content = _response_content(value)
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return content
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.info("decision twin returned non-json payload")
        return {}


def _response_content(value: Any) -> Any:
    if isinstance(value, (dict, str)):
        return value
    choices = getattr(value, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        return getattr(message, "content", None)
    return value


def _clean_token(value: Any, *, default: str = "") -> str:
    token = str(value or default).strip()
    return token[:120]


def _confidence(value: Any) -> float:
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0


def _evidence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in value if str(item or "").strip())
