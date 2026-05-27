"""Discord RAG persistence for YouTube summaries."""

from __future__ import annotations

from typing import Any

from gateway.discord_workspace import _write_rag_record, ensure_workspace
from gateway.discord_workspace_paths import utc_now

from . import context
from .models import SummaryResult


def save_summary_to_thread_rag(summary: SummaryResult) -> bool:
    channel_id = context.CHANNEL_ID.get().strip()
    if not channel_id:
        return False
    workspace = ensure_workspace(
        guild_id=context.GUILD_ID.get(),
        channel_id=channel_id,
        channel_name=context.CHANNEL_NAME.get(),
        thread_id=context.THREAD_ID.get(),
        thread_name=context.THREAD_NAME.get(),
    )
    record = _summary_record(summary)
    active_kind = "miho-discord-thread-rag" if workspace.thread_dir else "miho-discord-channel-rag"
    _write_rag_record(workspace.rag_dir, record, kind=active_kind)
    if workspace.thread_dir:
        parent = {
            **record,
            "thread_id": context.THREAD_ID.get(),
            "thread_name": context.THREAD_NAME.get(),
            "event_type": "youtube_summary",
        }
        _write_rag_record(workspace.channel_rag_dir, parent, kind="miho-discord-channel-rag")
    return True


def _summary_record(summary: SummaryResult) -> dict[str, Any]:
    text = "\n".join(
        [
            f"YouTube summary: {summary.short_title}",
            f"Video ID: {summary.video_id}",
            f"Original title: {summary.metadata.title}",
            f"Channel: {summary.metadata.channel}",
            f"Published: {summary.metadata.published_at or 'unknown'}",
            f"Tags: {', '.join(summary.tags)}",
            f"Topic: {summary.topic}",
            f"One-line: {summary.one_line_summary}",
            "Summary:",
            *summary.summary_lines,
            "Important points:",
            *summary.important_points,
            "Miho judgment:",
            summary.miho_judgment,
            "User-context help:",
            *summary.profile_help,
            "Conclusion:",
            summary.conclusion,
        ]
    )
    return {
        "timestamp": utc_now(),
        "message_id": f"youtube:{summary.video_id}",
        "user_id": "miho",
        "user_name": "Miho",
        "role": "assistant",
        "event_type": "youtube_summary",
        "text": text,
    }
