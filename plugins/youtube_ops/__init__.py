"""YouTube operations plugin."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .context import capture_gateway_context
from .pre_gateway import youtube_preflight_decision
from .tools import _youtube_analyze_tool_handler, set_llm

logger = logging.getLogger(__name__)
YOUTUBE_PRE_GATEWAY_TIMEOUT_SECONDS = 180


def _capture_gateway_context(event: Any = None, **_: Any) -> dict[str, str]:
    capture_gateway_context(event)
    return {"action": "allow"}


async def _youtube_pre_gateway_dispatch(event: Any = None, **_: Any) -> dict[str, str]:
    capture_gateway_context(event)
    decision = youtube_preflight_decision(str(getattr(event, "text", "") or ""))
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

    return {"action": "respond", "text": _response_text(raw_result)}


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
