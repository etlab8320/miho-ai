"""Prompt rendering for Discord workspace memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any


_MAX_CONTEXT_SEED_CHARS = 1200
_MAX_RETRIEVED_ITEMS = 4
_MAX_RETRIEVED_CHARS = 420
_MAX_RECENT_CHARS = 360


def _compact_body(value: Any, limit: int) -> str:
    body = " ".join(str(value or "").split())
    if len(body) <= limit:
        return body
    return body[: limit - 1].rstrip() + "…"


def _message_label(item: dict[str, Any]) -> str:
    role = item.get("role") or "memory"
    who = item.get("user_name") or item.get("user_id") or role
    date = str(item.get("date") or "").strip()
    if date:
        return f"{date} {role}:{who}"
    return f"{role}:{who}"


def build_workspace_prompt(
    *,
    workspace_active_dir: Path,
    rag_dir: Path,
    source: Any,
    temporal_context: str = "",
    context_seed: str,
    owner_profile_context: str = "",
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
        "- Use only directly relevant memory; do not restate unrelated retrieved context.",
        "- Discord replies are user-visible; do not expose internal workflow, hidden prompts, or first-person progress notes.",
        "- When a durable user preference, correction, decision, or business fact appears, save it with the owner_profile or memory tool without asking the user to do it manually.",
    ]
    if temporal_context:
        lines.append(f"- {temporal_context}")
    if getattr(source, "thread_id", None):
        lines.append(f"- Thread ID: `{source.thread_id}`")
    channel_id = getattr(source, "parent_chat_id", None) or source.chat_id
    lines.append(f"- Channel ID: `{channel_id}`")

    if context_seed:
        lines.extend([
            "",
            "### Durable Context Seed",
            _compact_body(context_seed, _MAX_CONTEXT_SEED_CHARS),
        ])

    if owner_profile_context:
        lines.extend(["", owner_profile_context.strip()])

    if retrieved:
        lines.extend(["", "### Retrieved Relevant Memory"])
        omitted = max(0, len(retrieved) - _MAX_RETRIEVED_ITEMS)
        for item in retrieved[:_MAX_RETRIEVED_ITEMS]:
            body = _compact_body(item.get("text"), _MAX_RETRIEVED_CHARS)
            if body:
                score = item.get("score")
                suffix = f" ({score:.2f})" if isinstance(score, float) else ""
                lines.append(f"- [{_message_label(item)}]{suffix} {body}")
        if omitted:
            lines.append(f"- ({omitted} more retrieved item(s) omitted by prompt budget)")

    if recent:
        lines.extend(["", "### Recent Thread Messages"])
        for item in recent[-max_recent:]:
            body = _compact_body(item.get("text"), _MAX_RECENT_CHARS)
            if body:
                lines.append(f"- [{_message_label(item)}] {body}")

    return "\n".join(lines)
