"""Prompt rendering for Discord workspace memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_workspace_prompt(
    *,
    workspace_active_dir: Path,
    rag_dir: Path,
    source: Any,
    context_seed: str,
    recent: list[dict[str, Any]],
    retrieved: list[dict[str, Any]],
    max_recent: int,
) -> str:
    """Render the lightweight prompt injected for a Discord turn."""
    lines = [
        "## Miho Discord Workspace RAG",
        "",
        f"- Workspace: `{workspace_active_dir}`",
        f"- RAG index: `{rag_dir / 'index.json'}`",
        "- Treat this as the persistent channel/thread memory for this Discord context.",
    ]
    if getattr(source, "thread_id", None):
        lines.append(f"- Thread ID: `{source.thread_id}`")
    channel_id = getattr(source, "parent_chat_id", None) or source.chat_id
    lines.append(f"- Channel ID: `{channel_id}`")

    if context_seed:
        lines.extend(["", "### Durable Context Seed", context_seed[:1800]])

    if retrieved:
        lines.extend(["", "### Retrieved Relevant Memory"])
        for item in retrieved:
            role = item.get("role") or "memory"
            who = item.get("user_name") or item.get("user_id") or role
            body = item.get("text") or ""
            if body:
                score = item.get("score")
                suffix = f" ({score:.2f})" if isinstance(score, float) else ""
                lines.append(f"- [{role}:{who}]{suffix} {body}")

    if recent:
        lines.extend(["", "### Recent Thread Messages"])
        for item in recent[-max_recent:]:
            role = item.get("role") or "user"
            who = item.get("user_name") or item.get("user_id") or role
            body = item.get("text") or ""
            if body:
                lines.append(f"- [{role}:{who}] {body}")

    return "\n".join(lines)
