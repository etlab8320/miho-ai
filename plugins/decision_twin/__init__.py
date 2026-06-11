"""LLM-backed pre-gateway decision twin for Miho routing."""

from __future__ import annotations

import logging
import importlib
import sys
from pathlib import Path
from typing import Any

from .domain_guard import has_domain_conflict, should_skip_clarify_response
from .router import (
    DECISION_TWIN_TASK,
    DecisionResolver,
    build_decision_messages,
    default_decision_resolver,
    parse_decision_payload,
    route_result_text,
    should_route_decision,
)


logger = logging.getLogger(__name__)
_ROUTE_PRIORITY = 85


async def _decision_twin_pre_gateway_dispatch(
    event: Any = None,
    gateway: Any = None,
    resolver: DecisionResolver = default_decision_resolver,
    owner_context_builder: Any = None,
    **_: Any,
) -> dict[str, object]:
    if not _should_run(event, gateway):
        return {"action": "allow"}
    text = str(getattr(event, "text", "") or "").strip()
    owner_context = _owner_context(text, owner_context_builder)
    messages = build_decision_messages(
        user_text=text,
        owner_context=owner_context,
        turn_context=_turn_context(event),
    )
    try:
        raw = await resolver(messages)
    except Exception as exc:
        logger.info("decision twin resolver skipped: %s", exc)
        return {"action": "allow"}
    decision = parse_decision_payload(raw)
    if has_domain_conflict(decision, user_text=text, owner_context=owner_context, turn_context=_turn_context(event)):
        logger.info(
            "decision twin blocked domain conflict: tool=%s intent=%s",
            decision.required_tool,
            decision.intent,
        )
        return {"action": "allow"}
    if should_route_decision(decision):
        _mark_required_tool_route(event, decision.required_tool)
        return {
            "action": "rewrite",
            "text": route_result_text(text, decision),
            "route": "decision_twin",
            "reason": "llm_judge",
            "intent": decision.intent,
            "confidence": decision.confidence,
            "evidence": list(decision.evidence),
            "required_tool": decision.required_tool,
            "priority": _ROUTE_PRIORITY,
        }
    turn_context = _turn_context(event)
    if (
        decision.action == "clarify"
        and should_skip_clarify_response(user_text=text, owner_context=owner_context, turn_context=turn_context)
    ):
        logger.info("decision twin skipped clarify for complete score context: intent=%s", decision.intent)
        return {"action": "allow"}
    if decision.action == "clarify" and decision.confidence >= 0.75 and decision.user_message:
        return {
            "action": "respond",
            "text": decision.user_message,
            "route": "decision_twin",
            "reason": "llm_clarify",
            "intent": decision.intent or "conversation.clarify",
            "confidence": decision.confidence,
            "evidence": list(decision.evidence),
            "priority": -10,
        }
    return {"action": "allow"}


def _mark_required_tool_route(event: Any, required_tool: str) -> None:
    for module_name in _guard_module_names():
        try:
            module = sys.modules.get(module_name) or importlib.import_module(module_name)
        except Exception:
            continue
        marker = getattr(module, "mark_hakjong_report_required_route", None)
        if callable(marker):
            marker(event, required_tool=required_tool)
            return
    logger.info("decision twin route marker skipped: hakjong report guard unavailable")


def _guard_module_names() -> tuple[str, ...]:
    root = __name__.split(".", 1)[0]
    names = [
        f"{root}.academy_ops.hakjong_report_guard",
        "plugins.academy_ops.hakjong_report_guard",
        "miho_plugins.academy_ops.hakjong_report_guard",
    ]
    return tuple(dict.fromkeys(names))


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
    except Exception as exc:
        logger.info("decision twin auth check failed closed: %s", exc)
        return False


def _owner_context(text: str, builder: Any = None) -> str:
    if callable(builder):
        return str(builder(text) or "").strip()
    try:
        from gateway.owner_profile_context import build_relevant_owner_profile_context

        return build_relevant_owner_profile_context(text)
    except Exception as exc:
        logger.info("decision twin owner context skipped: %s", exc)
        return ""


def _turn_context(event: Any) -> dict[str, Any]:
    media = [_media_summary(item) for item in getattr(event, "media_urls", None) or []]
    return {
        "media": [item for item in media if item],
        "reply_to_text": _compact(getattr(event, "reply_to_text", "")),
        "channel_context": _compact(getattr(event, "channel_context", "")),
        "channel_prompt": _compact(getattr(event, "channel_prompt", ""), limit=600),
    }


def _media_summary(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    suffix = path.suffix.lower()
    return suffix or raw[:40]


def _compact(value: Any, *, limit: int = 420) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def register(ctx: Any) -> None:
    ctx.register_hook("pre_gateway_dispatch", _decision_twin_pre_gateway_dispatch)
    ctx.register_auxiliary_task(
        key=DECISION_TWIN_TASK,
        display_name="Miho decision twin",
        description="LLM judge for gateway intent, context, and required tool routing",
        defaults={"provider": "auto", "timeout": 18, "extra_body": {"reasoning": {"effort": "low"}}},
    )


__all__ = ["_decision_twin_pre_gateway_dispatch", "register"]
