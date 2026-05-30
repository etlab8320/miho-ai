"""YouTube operations plugin."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from .context import capture_gateway_context
from .pre_gateway import youtube_preflight_decision
from .tools import _youtube_analyze_tool_handler, set_llm

logger = logging.getLogger(__name__)
YOUTUBE_PRE_GATEWAY_TIMEOUT_SECONDS = 180


def _capture_gateway_context(event: Any = None, **_: Any) -> dict[str, str]:
    capture_gateway_context(event)
    return {"action": "allow"}


async def _youtube_pre_gateway_dispatch(event: Any = None, **kwargs: Any) -> dict[str, str]:
    capture_gateway_context(event)
    text = str(getattr(event, "text", "") or "")
    decision = youtube_preflight_decision(text)
    if decision is None:
        return {"action": "allow"}
    try:
        raw_result = await asyncio.wait_for(
            asyncio.to_thread(_youtube_analyze_tool_handler, decision.args),
            timeout=YOUTUBE_PRE_GATEWAY_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return {"action": "respond", "text": "유튜브 분석이 오래 걸리고 있어. 잠시 후 다시 보내줘."}
    except Exception as exc:
        logger.warning("YouTube pre-gateway analysis failed: %s", exc)
        return {"action": "respond", "text": "유튜브 분석 중 문제가 생겼어. 잠시 후 다시 시도해줘."}

    response = _response_text(raw_result)
    # Record this HANDLED turn so the body agent sees it next turn — without it,
    # a follow-up ("그 영상에서 아까 그 부분") loses the analysis context, same
    # bug we fixed in academy_ops. Best-effort; never break the reply.
    _persist_handled_turn(kwargs.get("session_store"), event, text, response)
    return {"action": "respond", "text": response}


def _persist_handled_turn(session_store: Any, event: Any, question: str, answer: str) -> None:
    if session_store is None or not str(answer or "").strip():
        return
    source = getattr(event, "source", None)
    if source is None:
        return
    try:
        session_id = session_store.get_or_create_session(source).session_id
        ts = datetime.now().isoformat()
        session_store.append_to_transcript(session_id, {"role": "user", "content": question, "timestamp": ts})
        session_store.append_to_transcript(session_id, {"role": "assistant", "content": answer, "timestamp": ts})
    except Exception as exc:  # noqa: BLE001 - a transcript write must never break the reply
        logger.debug("youtube HANDLED transcript persist failed: %s", exc)


def _response_text(raw_result: str) -> str:
    try:
        payload = json.loads(raw_result)
    except (TypeError, json.JSONDecodeError):
        return str(raw_result or "").strip() or "유튜브 분석 결과를 만들지 못했어."
    if not isinstance(payload, dict):
        return "유튜브 분석 결과를 만들지 못했어."
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return "유튜브 분석 결과를 만들지 못했어."


def register(ctx: Any) -> None:
    set_llm(ctx.llm)
    ctx.register_hook("pre_gateway_dispatch", _youtube_pre_gateway_dispatch)
    ctx.register_tool(
        name="youtube_analyze_video",
        toolset="youtube_ops",
        schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "YouTube URL or raw 11-character video ID.",
                },
                "render_card": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to render a Discord-ready PNG summary card.",
                },
                "force_refresh": {
                    "type": "boolean",
                    "default": False,
                    "description": "Ignore cached transcript summary for this video_id.",
                },
                "languages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Preferred transcript languages. Defaults to Korean then English.",
                },
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        handler=_youtube_analyze_tool_handler,
        description=(
            "Analyze a YouTube video from its full transcript, cache by video_id, save a compact "
            "RAG record with a unique short title/tags, and optionally render a Goyang Deogyang "
            "PNG card. Use for YouTube summary, key-point extraction, and image-card requests. "
            "Never summarize from URL alone."
        ),
    )
