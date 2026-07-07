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
    needs_region_question: bool | None = None
    region_value: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
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
        timeout=30,
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
            "needs_region_question": "true|false — 사용자 요청이 학교 추천(수시/실기/교과 추천·선별)인데 문장과 turn_context 어디에도 지역(광역명들 또는 '전국') 언급이 없으면 true",
            "region_value": "사용자가 언급한 지역 표현 그대로 (광역 단위 쉼표 구분, 예: '서울, 경기, 인천, 강원, 대전' 또는 '전국'). 언급 없으면 빈 문자열",
            "tool_args": "required_tool 호출에 필요한 인자를 JSON object로 채워라. 확실한 값만 넣고, 불확실하면 빈 object",
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
        needs_region_question=_tri_bool(payload.get("needs_region_question")),
        region_value=str(payload.get("region_value") or "").strip()[:120],
        tool_args=_clean_tool_args(payload.get("tool_args")),
        evidence=_evidence(payload.get("evidence")),
        tool_instruction=str(payload.get("tool_instruction") or "").strip(),
        user_message=str(payload.get("user_message") or "").strip(),
    )


def should_route_decision(decision: LlmRouteDecision) -> bool:
    if decision.action not in {"route", "execute", "rewrite"}:
        return False
    if not decision.required_tool:
        return False
    if decision.required_tool not in decision_tool_contracts():
        return False
    return decision.confidence >= MIN_ROUTE_CONFIDENCE


def annotate_result_text(user_text: str, decision: LlmRouteDecision) -> str:
    evidence = ", ".join(decision.evidence) if decision.evidence else "LLM decision twin"
    hint_lines = [
        "[라우팅 지시 — 본문 에이전트는 이 도구 경로를 먼저 실행한다]",
        f"의도: {decision.intent or decision.required_tool}",
    ]
    if decision.required_tool:
        hint_lines.append(f"필수 실행 도구: {decision.required_tool}")
        hint_lines.append("MUST use required_tool before final answer.")
    if decision.tool_instruction:
        hint_lines.append(f"실행 지시: {decision.tool_instruction}")
    if decision.tool_args:
        hint_lines.append(
            "도구 인자(JSON): "
            + json.dumps(decision.tool_args, ensure_ascii=False, sort_keys=True)
        )
    if decision.region_value:
        hint_lines.append(
            f"지역: {decision.region_value} — 추천/패키지 도구 호출 시 region 인자에 이 값을 그대로 넣어라"
        )
    hint_lines.append(f"근거: {evidence}")
    return f"{user_text}\n\n" + "\n".join(hint_lines)


def _system_prompt() -> str:
    return (
        "너는 Miho 게이트웨이 앞단의 LLM decision twin이다. 사용자에게 직접 답하지 말고 JSON만 반환해. "
        "키워드 하나로 라우팅하지 말고 현재 문장, 첨부, reply/thread context, owner_memory, tool_contracts를 함께 읽어라. "
        "사용자의 실제 job을 추론하고, 전용 도구나 MEDIA 계약이 필요한 경우 action=route와 required_tool을 채워라. "
        "생기부/학종/학원DB/유튜브/파일전달처럼 근거 도구가 필요한 업무는 기억이나 추측만으로 답하게 두지 마라. "
        "사용자가 PDF를 처음부터 요청했거나 직전 답변/스레드 내용을 PDF로 정리해달라고 하면 "
        "tool_contracts에서 고정 입시 패키지에 해당하는지 먼저 확인하고, 고정 패키지가 아니면 "
        "새 제작물 경로인 html_pdf_quality_gate를 선택해라. 이 경우 PyMuPDF/ReportLab/fitz 좌표 스크립트가 아니라 "
        "HTML-first 원본 작성 -> html_pdf_quality_gate -> media_delivery_contract 흐름을 tool_instruction에 적어라. "
        "단, 작년 공식 모집요강·전년도 입학처 PDF·작년 산식·개인 산식 비교·작년 점수와 올해 점수 차이를 묻는 "
        "수시 요청은 PDF 표면 요청이 아니라 수시 산식 재계산 목표다. 이 경우 required_tool은 "
        "susi26_rule_lookup을 우선하고, tool_instruction에는 작년 구조 확인 -> susi27_rule_lookup/current "
        "university_id 확인 -> susi27_score_calculate -> 계산표와 차이 원인 설명을 적어라. "
        "pixel_document_evidence는 공식 PDF 원문 보조 근거일 수는 있지만 개인 산식 비교의 최종 계산 도구로 선택하지 마라. "
        "현재 상태를 직접 확인해야 하는 서버, SSH, IP, 프로세스, 포트, 크론, 로그 요청은 "
        "과거 대화 회상이 아니라 terminal 계약을 우선한다. session_search는 과거에 사용자가 말한 값이나 "
        "이전 세션 기록을 찾을 때만 선택하고, 회상 결과를 현재 상태 증거로 확정하지 마라. "
        "확신이 낮거나 필수 인자가 없으면 action=allow로 둔다. "
        "기존 추천/PDF에 대한 수정·누락·성별 오류·조건전형 예외 후속 지시는 새 추천의 지역 누락으로 보지 말고, "
        "직전 context를 확인하도록 관련 추천 도구/terminal로 route하거나 action=allow로 본문 에이전트에 넘겨라. "
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


def _tri_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in ("true", "yes", "1"):
        return True
    if text in ("false", "no", "0"):
        return False
    return None


def _confidence(value: Any) -> float:
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0


def _clean_tool_args(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if len(encoded) > 2000:
            return {}
        parsed = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key)[:80]: item for key, item in parsed.items() if str(key).strip()}


def _evidence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in value if str(item or "").strip())
