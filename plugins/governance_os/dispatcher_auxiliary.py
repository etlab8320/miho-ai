"""LLM auxiliary dispatcher helpers for Governance OS routing."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, cast

from .dispatcher_models import DispatchDecision, RouteCandidate
from .registry import GovernanceRegistry
from .router_map import build_router_map
from .versioning import load_runtime_registry

AUXILIARY_CONFIDENCE_THRESHOLD = 0.7


async def call_auxiliary_dispatcher(
    *,
    task: str,
    user_text: str,
    candidate_decision: DispatchDecision,
    candidates: tuple[RouteCandidate, ...],
    registry: GovernanceRegistry | None = None,
    turn_context: dict[str, Any] | None = None,
    call_llm: Callable[..., Awaitable[Any]] | None = None,
    extract_content: Callable[[Any], Any] | None = None,
) -> dict[str, object]:
    if call_llm is None or extract_content is None:
        from agent.auxiliary_client import async_call_llm, extract_content_or_reasoning

        call = async_call_llm if call_llm is None else call_llm
        extract = extract_content_or_reasoning if extract_content is None else extract_content
    else:
        call = call_llm
        extract = extract_content

    response = await call(
        task=task,
        messages=[
            {
                "role": "system",
                "content": (
                    "Return JSON only. Select the best Governance OS playbook for the user request. "
                    "Use route_map semantically; candidate-scorer hints are evidence, not hard limits. "
                    "Use action=allow only when no governed playbook applies. "
                    "운영 진단, 현재 서버/IP/SSH/크론/프로세스/로그 확인은 그 자체로 dev_code_update가 아니다. "
                    "dev_code_update는 사용자가 저장소 코드, 설정, 배포, 패치를 실제로 바꾸라고 한 경우에만 선택한다."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_text": user_text,
                        "turn_context": turn_context or {},
                        "route_map": build_router_map(registry or load_runtime_registry()),
                        "candidate_scorer": _decision_metadata(candidate_decision),
                        "candidates": [_candidate_metadata(item) for item in candidates],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0,
        max_tokens=400,
        timeout=8,
    )
    payload = _loads_object(extract(response))
    if payload is None:
        raise ValueError("auxiliary dispatcher returned invalid JSON")
    return payload


def decision_from_auxiliary_payload(
    registry: GovernanceRegistry,
    payload: dict[str, object],
    *,
    fallback: DispatchDecision,
    candidates: tuple[RouteCandidate, ...] = (),
    task_name: str,
) -> DispatchDecision | None:
    action = str(payload.get("action") or "route").strip().casefold()
    if action == "allow":
        return DispatchDecision(
            action="allow",
            confidence=_float(payload.get("confidence"), default=fallback.confidence),
            reason=str(payload.get("reason") or "auxiliary_dispatcher_allow"),
            routing_source=task_name,
        )
    if action not in {"route", "rewrite", "execute"}:
        return None
    playbook_key = str(payload.get("playbook_key") or "").strip()
    if not playbook_key or playbook_key not in registry.playbooks:
        return None
    candidate_keys = {candidate.playbook_key for candidate in candidates}
    if candidate_keys and playbook_key not in candidate_keys and not _has_map_grade_evidence(payload):
        return None
    confidence = _float(payload.get("confidence"), default=fallback.confidence)
    if confidence < AUXILIARY_CONFIDENCE_THRESHOLD:
        return None
    playbook = registry.get_playbook(playbook_key)
    matched = _tuple_str(payload.get("matched_triggers")) or fallback.matched_triggers
    return DispatchDecision(
        action="rewrite",
        playbook_key=playbook.key,
        domain=playbook.domain,
        confidence=min(1.0, max(AUXILIARY_CONFIDENCE_THRESHOLD, confidence)),
        matched_triggers=matched,
        missing_context=playbook.required_context,
        required_tools=playbook.required_tools,
        forbidden_tools=playbook.forbidden_tools,
        agent_chain=playbook.agent_chain,
        review_gates=playbook.review_gates,
        retry_policy=playbook.retry_policy,
        delivery_format=playbook.delivery_format,
        reason=str(payload.get("reason") or "auxiliary_dispatcher"),
        routing_source=task_name,
    )


def _has_map_grade_evidence(payload: dict[str, object]) -> bool:
    confidence = _float(payload.get("confidence"), default=0.0)
    if confidence < 0.9:
        return False
    return bool(_tuple_str(payload.get("evidence")))


def _decision_metadata(decision: DispatchDecision) -> dict[str, object]:
    return {
        "playbook_key": decision.playbook_key,
        "confidence": decision.confidence,
        "required_tools": list(decision.required_tools),
        "matched_triggers": list(decision.matched_triggers),
        "retry_policy": decision.retry_policy,
        "delivery_format": decision.delivery_format,
    }


def _candidate_metadata(candidate: RouteCandidate) -> dict[str, object]:
    return {
        "playbook_key": candidate.playbook_key,
        "score": candidate.score,
        "matched_triggers": list(candidate.matched_triggers),
    }


def _loads_object(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None


def _tuple_str(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    return (text,) if text else ()


def _float(value: object, *, default: float) -> float:
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
