"""Deterministic playbook dispatcher for Governance OS."""

from __future__ import annotations

import logging
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any, Literal, cast

from .dispatch_context import build_dispatch_turn_context
from .models import PolicyDecision
from .registry import GovernanceRegistry
from .risk import evaluate_request_risk
from .router_map import build_router_map
from .versioning import load_runtime_registry


DispatchAction = Literal["allow", "rewrite"]
_ROUTE_PRIORITY = 70
_DISPATCHER_TASK = "miho_governance_dispatcher"
_AUXILIARY_CONFIDENCE_THRESHOLD = 0.7
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DispatchDecision:
    action: DispatchAction
    playbook_key: str = ""
    domain: str = ""
    confidence: float = 0.0
    matched_triggers: tuple[str, ...] = field(default_factory=tuple)
    missing_context: tuple[str, ...] = field(default_factory=tuple)
    required_tools: tuple[str, ...] = field(default_factory=tuple)
    forbidden_tools: tuple[str, ...] = field(default_factory=tuple)
    agent_chain: tuple[str, ...] = field(default_factory=tuple)
    review_gates: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""
    routing_source: str = "deterministic"


@dataclass(frozen=True)
class RouteCandidate:
    score: float
    playbook_key: str
    matched_triggers: tuple[str, ...] = field(default_factory=tuple)


def dispatch_request(
    registry: GovernanceRegistry,
    text: str,
    *,
    available_context: tuple[str, ...] = (),
) -> DispatchDecision:
    blob = " ".join(str(text or "").casefold().split())
    if not blob:
        return DispatchDecision(action="allow", reason="empty_text")

    candidates = _score_candidates(registry, blob)
    if not candidates:
        return DispatchDecision(action="allow", reason="no_playbook_match")
    top = candidates[0]
    playbook = registry.get_playbook(top.playbook_key)
    confidence = min(1.0, 0.55 + (top.score * 0.2))
    available = {item.strip() for item in available_context if item.strip()}
    missing = tuple(item for item in playbook.required_context if item not in available)
    return DispatchDecision(
        action="rewrite" if confidence >= 0.7 else "allow",
        playbook_key=playbook.key,
        domain=playbook.domain,
        confidence=confidence,
        matched_triggers=top.matched_triggers,
        missing_context=missing,
        required_tools=playbook.required_tools,
        forbidden_tools=playbook.forbidden_tools,
        agent_chain=playbook.agent_chain,
        review_gates=playbook.review_gates,
        reason="trigger_match",
    )


def build_governance_rewrite(original_text: str, decision: DispatchDecision) -> str:
    if decision.action != "rewrite" or not decision.playbook_key:
        return original_text
    hints = [
        "Governance OS routing:",
        f"- playbook: {decision.playbook_key}",
        f"- domain: {decision.domain}",
        f"- required_tools: {', '.join(decision.required_tools) or '-'}",
        "- MUST use required_tools before final delivery; do not present governed output as complete until review_gates pass.",
        f"- review_gates: {', '.join(decision.review_gates) or '-'}",
        f"- missing_context: {', '.join(decision.missing_context) or '-'}",
    ]
    if decision.missing_context:
        hints.append(
            "- MUST resolve missing_context before calling required_tools; ask a Korean clarification if missing data cannot be inferred safely."
        )
    if "media_delivery_contract" in decision.required_tools:
        hints.append(
            "- Do not handwrite MEDIA tags; call media_delivery_contract and use its delivery_text."
        )
    return str(original_text).strip() + "\n\n" + "\n".join(hints)


def build_approval_response(risk: PolicyDecision) -> str:
    return (
        risk.message_ko
        + "\n\n테스트 결과와 롤백 방법을 확인한 뒤 명시적으로 승인해 주세요. "
        "승인 전에는 작업을 진행하지 않습니다."
    )


async def governance_pre_gateway_dispatch(
    event: Any = None,
    gateway: Any = None,
    **_: Any,
) -> dict[str, object]:
    if not _should_run(event, gateway):
        return {"action": "allow"}
    text = str(getattr(event, "text", "") or "").strip()
    registry = load_runtime_registry()
    decision = dispatch_request(registry, text)
    candidates = _score_candidates(registry, " ".join(text.casefold().split()))
    turn_context = build_dispatch_turn_context(event)
    if _needs_auxiliary_dispatch(decision, candidates):
        decision = await _with_auxiliary_dispatcher(
            registry=registry,
            text=text,
            decision=decision,
            candidates=candidates,
            turn_context=turn_context,
        )
    if decision.action != "rewrite":
        return {"action": "allow"}
    risk = evaluate_request_risk(
        registry,
        playbook_key=decision.playbook_key,
        user_text=text,
        tool_name=decision.required_tools[0] if decision.required_tools else "",
    )
    if risk.action == "require_approval":
        _record_approval_hold(event, text, decision, risk)
        return {
            "action": "respond",
            "text": build_approval_response(risk),
            "route": "governance_os",
            "reason": risk.reason,
            "intent": decision.playbook_key,
            "confidence": decision.confidence,
            "evidence": list(decision.matched_triggers) + list(risk.evidence),
            "missing_context": list(decision.missing_context),
            "required_tool": "",
            "priority": _ROUTE_PRIORITY + 10,
            "approval_required": True,
            "message": risk.message_ko,
            "routing_source": decision.routing_source,
        }
    return {
        "action": "rewrite",
        "text": build_governance_rewrite(text, decision),
        "route": "governance_os",
        "reason": decision.reason,
        "intent": decision.playbook_key,
        "confidence": decision.confidence,
        "evidence": list(decision.matched_triggers),
        "missing_context": list(decision.missing_context),
        "required_tool": decision.required_tools[0] if decision.required_tools else "",
        "priority": _ROUTE_PRIORITY,
        "routing_source": decision.routing_source,
    }


def _score_candidates(registry: GovernanceRegistry, blob: str) -> tuple[RouteCandidate, ...]:
    candidates = [
        RouteCandidate(score, playbook_key, matched)
        for score, playbook_key, matched in (
            _score_playbook(playbook_key, registry, blob)
            for playbook_key in sorted(registry.playbooks)
        )
        if score > 0
    ]
    return tuple(sorted(candidates, key=lambda item: (item.score, item.playbook_key), reverse=True))


def _needs_auxiliary_dispatch(
    decision: DispatchDecision,
    candidates: tuple[RouteCandidate, ...],
) -> bool:
    if decision.action == "allow" and not candidates:
        return True
    if decision.action != "rewrite":
        return False
    if len(candidates) >= 2 and candidates[0].score - candidates[1].score <= 0.75:
        return True
    return _AUXILIARY_CONFIDENCE_THRESHOLD <= decision.confidence < 0.9


async def _with_auxiliary_dispatcher(
    *,
    registry: GovernanceRegistry,
    text: str,
    decision: DispatchDecision,
    candidates: tuple[RouteCandidate, ...],
    turn_context: dict[str, Any] | None = None,
) -> DispatchDecision:
    try:
        payload = await _call_auxiliary_dispatcher(
            task=_DISPATCHER_TASK,
            user_text=text,
            registry=registry,
            deterministic_decision=decision,
            candidates=candidates,
            turn_context=turn_context,
        )
    except Exception as exc:
        logger.warning("Governance auxiliary dispatcher unavailable: %s", exc)
        return replace(decision, routing_source="deterministic_fallback")
    refined = _decision_from_auxiliary_payload(
        registry,
        payload,
        fallback=decision,
        candidates=candidates,
    )
    return refined if refined is not None else replace(decision, routing_source="deterministic_fallback")


async def _call_auxiliary_dispatcher(
    *,
    task: str,
    user_text: str,
    deterministic_decision: DispatchDecision,
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
                    "Use route_map semantically; deterministic candidates are hints, not hard limits. "
                    "Use action=allow only when no governed playbook applies."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_text": user_text,
                        "turn_context": turn_context or {},
                        "route_map": build_router_map(registry or load_runtime_registry()),
                        "deterministic": _decision_metadata(deterministic_decision),
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


def _decision_from_auxiliary_payload(
    registry: GovernanceRegistry,
    payload: dict[str, object],
    *,
    fallback: DispatchDecision,
    candidates: tuple[RouteCandidate, ...] = (),
) -> DispatchDecision | None:
    action = str(payload.get("action") or "route").strip().casefold()
    if action == "allow":
        return DispatchDecision(
            action="allow",
            confidence=_float(payload.get("confidence"), default=fallback.confidence),
            reason=str(payload.get("reason") or "auxiliary_dispatcher_allow"),
            routing_source=_DISPATCHER_TASK,
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
    if confidence < _AUXILIARY_CONFIDENCE_THRESHOLD:
        return None
    playbook = registry.get_playbook(playbook_key)
    matched = _tuple_str(payload.get("matched_triggers")) or fallback.matched_triggers
    return DispatchDecision(
        action="rewrite",
        playbook_key=playbook.key,
        domain=playbook.domain,
        confidence=min(1.0, max(_AUXILIARY_CONFIDENCE_THRESHOLD, confidence)),
        matched_triggers=matched,
        missing_context=playbook.required_context,
        required_tools=playbook.required_tools,
        forbidden_tools=playbook.forbidden_tools,
        agent_chain=playbook.agent_chain,
        review_gates=playbook.review_gates,
        reason=str(payload.get("reason") or "auxiliary_dispatcher"),
        routing_source=_DISPATCHER_TASK,
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


def _score_playbook(
    playbook_key: str,
    registry: GovernanceRegistry,
    blob: str,
) -> tuple[float, str, tuple[str, ...]]:
    playbook = registry.get_playbook(playbook_key)
    score = 0.0
    matched: list[str] = []
    for trigger in playbook.triggers:
        needle = trigger.casefold().strip()
        if not needle:
            continue
        words = [part for part in needle.split() if len(part) >= 2]
        if needle in blob:
            score += 2.0
            matched.append(trigger)
        elif len(words) >= 2 and all(word in blob for word in words):
            score += 1.4
            matched.append(trigger)
    return score, playbook_key, tuple(matched)


def _record_approval_hold(
    event: Any,
    user_text: str,
    decision: DispatchDecision,
    risk: PolicyDecision,
) -> None:
    try:
        from .ledger import OutcomeLedgerEntry, record_outcome

        record_outcome(
            OutcomeLedgerEntry(
                request_id=_request_id(event),
                playbook_key=decision.playbook_key,
                agent_chain=decision.agent_chain,
                tools_used=(),
                review_status="approval_required",
                failures=(risk.reason,),
                user_feedback=_compact_text(user_text),
            )
        )
    except Exception as exc:
        logger.warning("approval hold ledger record failed: %s", exc, exc_info=True)


def _request_id(event: Any) -> str:
    source = getattr(event, "source", None)
    platform_value = getattr(getattr(source, "platform", None), "value", None)
    platform = str(platform_value or getattr(source, "platform", "") or "gateway").strip()
    chat_id = str(getattr(source, "chat_id", "") or "").strip()
    message_id = str(
        getattr(event, "message_id", "") or getattr(source, "message_id", "") or ""
    ).strip()
    parts = [part for part in (platform, chat_id, message_id) if part]
    return ":".join(parts) if parts else "gateway-approval-hold"


def _compact_text(text: str, *, limit: int = 240) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def _should_run(event: Any, gateway: Any) -> bool:
    text = str(getattr(event, "text", "") or "").strip()
    if not text or text.startswith("/"):
        return False
    source = getattr(event, "source", None)
    if source is None or gateway is None:
        return False
    auth_fn = getattr(gateway, "_is_user_authorized", None)
    if not callable(auth_fn):
        return False
    try:
        return bool(auth_fn(source))
    except Exception:
        return False
