"""LLM-backed pre-gateway decision twin for Miho routing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .router import (
    DECISION_TWIN_TASK,
    DecisionResolver,
    annotate_result_text,
    build_decision_messages,
    default_decision_resolver,
    parse_decision_payload,
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
    if should_route_decision(decision):
        return {
            "action": "rewrite",
            "text": annotate_result_text(text, decision),
            "route": "decision_twin",
            "reason": "llm_judge",
            "intent": decision.intent,
            "confidence": decision.confidence,
            "evidence": list(decision.evidence),
            "required_tool": decision.required_tool,
            "priority": _ROUTE_PRIORITY,
        }
    return {"action": "allow"}


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
