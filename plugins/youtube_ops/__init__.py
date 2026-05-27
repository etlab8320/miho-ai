"""YouTube operations plugin."""

from __future__ import annotations

from typing import Any

from .context import capture_gateway_context
from .tools import _youtube_analyze_tool_handler, set_llm


def _capture_gateway_context(event: Any = None, **_: Any) -> dict[str, str]:
    capture_gateway_context(event)
    return {"action": "allow"}


def register(ctx: Any) -> None:
    set_llm(ctx.llm)
    ctx.register_hook("pre_gateway_dispatch", _capture_gateway_context)
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
