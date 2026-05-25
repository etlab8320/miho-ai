"""Discord workspace storage for Miho gateway context."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils import atomic_json_write
from gateway.discord_workspace_archive import (
    archive_workspace_for_channel,
    archive_workspace_for_thread,
)
from gateway.discord_workspace_paths import (
    clean_component,
    discord_root,
    utc_now,
    workspace_child,
    write_manifest,
)
from gateway.discord_workspace_prompt import build_workspace_prompt
from gateway.discord_workspace_vectors import index_rag_record, retrieve_rag_context


_MAX_CONTEXT_MESSAGES = 8
_MAX_MESSAGE_CHARS = 500
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscordWorkspace:
    root: Path
    channel_dir: Path
    thread_dir: Path | None

    @property
    def active_dir(self) -> Path:
        return self.thread_dir or self.channel_dir

    @property
    def rag_dir(self) -> Path:
        return self.active_dir / "rag"

    @property
    def channel_rag_dir(self) -> Path:
        return self.channel_dir / "rag"


def _ensure_rag(active_dir: Path, *, kind: str) -> None:
    rag_dir = active_dir / "rag"
    (rag_dir / "documents").mkdir(parents=True, exist_ok=True)
    index_path = rag_dir / "index.json"
    if not index_path.exists():
        index_data = {
            "version": 1,
            "kind": kind,
            "message_count": 0,
            "updated_at": utc_now(),
        }
        atomic_json_write(index_path, index_data, indent=2)
    context_path = active_dir / "context.md"
    if not context_path.exists():
        context_path.write_text(
            "# Miho Discord Context\n\n"
            "This file is the human-editable context seed for this Discord "
            "channel or thread. Add durable facts, decisions, links, and rules "
            "that Miho should keep in mind.\n",
            encoding="utf-8",
        )


def ensure_workspace(
    *,
    guild_id: Any = None,
    channel_id: Any,
    channel_name: Any = None,
    thread_id: Any = None,
    thread_name: Any = None,
    topic: str | None = None,
) -> DiscordWorkspace:
    """Create the channel/thread workspace and return its paths."""
    root = discord_root() / "guilds" / clean_component(
        guild_id, "direct"
    )
    channel_dir = workspace_child(root / "channels", channel_name, channel_id, "channel")
    channel_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(
        channel_dir / "channel.json",
        {
            "guild_id": str(guild_id or ""),
            "channel_id": str(channel_id or ""),
            "channel_name": str(channel_name or ""),
            "topic": topic or "",
        },
    )
    _ensure_rag(channel_dir, kind="miho-discord-channel-rag")

    thread_dir = None
    if thread_id:
        thread_dir = workspace_child(
            channel_dir / "threads",
            thread_name,
            thread_id,
            "thread",
        )
        thread_dir.mkdir(parents=True, exist_ok=True)
        write_manifest(
            thread_dir / "thread.json",
            {
                "guild_id": str(guild_id or ""),
                "parent_channel_id": str(channel_id or ""),
                "thread_id": str(thread_id or ""),
                "thread_name": str(thread_name or ""),
                "topic": topic or "",
            },
        )
        _ensure_rag(thread_dir, kind="miho-discord-thread-rag")

    return DiscordWorkspace(root=root, channel_dir=channel_dir, thread_dir=thread_dir)


def ensure_workspace_for_channel(channel: Any) -> DiscordWorkspace | None:
    channel_id = getattr(channel, "id", None)
    if channel_id is None:
        return None
    guild = getattr(channel, "guild", None)
    return ensure_workspace(
        guild_id=getattr(guild, "id", None),
        channel_id=channel_id,
        channel_name=getattr(channel, "name", None),
        topic=getattr(channel, "topic", None),
    )


def ensure_workspace_for_thread(thread: Any) -> DiscordWorkspace | None:
    thread_id = getattr(thread, "id", None)
    if thread_id is None:
        return None
    parent = getattr(thread, "parent", None)
    guild = getattr(thread, "guild", None) or getattr(parent, "guild", None)
    parent_id = getattr(parent, "id", None) or getattr(thread, "parent_id", None)
    return ensure_workspace(
        guild_id=getattr(guild, "id", None),
        channel_id=parent_id or thread_id,
        channel_name=getattr(parent, "name", None),
        thread_id=thread_id,
        thread_name=getattr(thread, "name", None),
        topic=getattr(parent, "topic", None),
    )


def _source_names(source: Any) -> tuple[str, str]:
    if getattr(source, "thread_id", None):
        thread_name = getattr(source, "chat_name", None) or str(source.thread_id)
        channel_name = getattr(source, "parent_chat_id", None) or "channel"
        return channel_name, thread_name
    return getattr(source, "chat_name", None) or str(source.chat_id), ""


def ensure_workspace_for_source(source: Any) -> DiscordWorkspace | None:
    if not source or not getattr(source, "chat_id", None):
        return None
    channel_name, thread_name = _source_names(source)
    return ensure_workspace(
        guild_id=getattr(source, "guild_id", None),
        channel_id=getattr(source, "parent_chat_id", None) or source.chat_id,
        channel_name=channel_name,
        thread_id=getattr(source, "thread_id", None),
        thread_name=thread_name,
        topic=getattr(source, "chat_topic", None),
    )


def _compact_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) > _MAX_MESSAGE_CHARS:
        compact = compact[: _MAX_MESSAGE_CHARS - 1].rstrip() + "…"
    return compact


def _append_message(path: Path, record: dict[str, Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                count = sum(1 for _ in fh)
        except OSError:
            count = 0
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return count + 1


def _recent_messages(path: Path, limit: int = _MAX_CONTEXT_MESSAGES) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except (OSError, UnicodeDecodeError):
        return []
    items: list[dict[str, Any]] = []
    for line in lines:
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            items.append(loaded)
    return items


def _write_rag_record(
    rag_dir: Path,
    record: dict[str, Any],
    *,
    kind: str,
) -> None:
    messages_path = rag_dir / "messages.jsonl"
    message_count = _append_message(messages_path, record)
    vector_metadata = index_rag_record(rag_dir, record)
    atomic_json_write(
        rag_dir / "index.json",
        {
            "version": 1,
            "kind": kind,
            "message_count": message_count,
            "messages_path": str(messages_path),
            "vector_count": vector_metadata["vector_count"],
            "vector_path": vector_metadata["vector_path"],
            "embedding_method": vector_metadata["embedding_method"],
            "updated_at": utc_now(),
        },
        indent=2,
    )


def record_turn_and_build_prompt(
    *,
    source: Any,
    text: str,
    message_id: str | None = None,
    timestamp: Any = None,
) -> str | None:
    """Persist a Discord message and return a compact RAG prompt block."""
    workspace = ensure_workspace_for_source(source)
    if workspace is None:
        return None

    record = {
        "timestamp": (
            timestamp.isoformat()
            if hasattr(timestamp, "isoformat")
            else str(timestamp or utc_now())
        ),
        "message_id": str(message_id or getattr(source, "message_id", "") or ""),
        "user_id": str(getattr(source, "user_id", "") or ""),
        "user_name": str(getattr(source, "user_name", "") or ""),
        "role": "user",
        "text": _compact_text(text),
    }
    active_kind = "miho-discord-thread-rag" if workspace.thread_dir else "miho-discord-channel-rag"
    _write_rag_record(workspace.rag_dir, record, kind=active_kind)

    if workspace.thread_dir:
        parent_record = {
            **record,
            "thread_id": str(getattr(source, "thread_id", "") or ""),
            "thread_name": str(getattr(source, "chat_name", "") or ""),
            "event_type": "thread_message",
        }
        _write_rag_record(
            workspace.channel_rag_dir,
            parent_record,
            kind="miho-discord-channel-rag",
        )

    context_seed = ""
    context_path = workspace.active_dir / "context.md"
    try:
        context_seed = context_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        context_seed = ""
    recent = _recent_messages(workspace.rag_dir / "messages.jsonl")
    retrieved = retrieve_rag_context(
        workspace.rag_dir,
        text,
        exclude_message_id=record["message_id"] or None,
    )
    top_score = max((float(item.get("score") or 0.0) for item in retrieved), default=0.0)
    scope = "thread" if workspace.thread_dir else "channel"
    logger.info(
        "Discord workspace RAG prompt: scope=%s recent=%d retrieved=%d top=%.3f",
        scope, len(recent), len(retrieved), top_score,
    )
    return build_workspace_prompt(
        workspace_active_dir=workspace.active_dir,
        rag_dir=workspace.rag_dir,
        source=source,
        context_seed=context_seed,
        recent=recent,
        retrieved=retrieved,
        max_recent=_MAX_CONTEXT_MESSAGES,
    )


def record_assistant_turn(
    *,
    source: Any,
    text: str,
    message_id: str | None = None,
    timestamp: Any = None,
) -> None:
    """Persist Miho's final Discord response into the workspace RAG."""
    workspace = ensure_workspace_for_source(source)
    if workspace is None:
        return
    record = {
        "timestamp": (
            timestamp.isoformat()
            if hasattr(timestamp, "isoformat")
            else str(timestamp or utc_now())
        ),
        "message_id": str(message_id or ""),
        "user_id": "miho",
        "user_name": "Miho",
        "role": "assistant",
        "text": _compact_text(text),
    }
    active_kind = "miho-discord-thread-rag" if workspace.thread_dir else "miho-discord-channel-rag"
    _write_rag_record(workspace.rag_dir, record, kind=active_kind)

    if workspace.thread_dir:
        parent_record = {
            **record,
            "thread_id": str(getattr(source, "thread_id", "") or ""),
            "thread_name": str(getattr(source, "chat_name", "") or ""),
            "event_type": "thread_message",
        }
        _write_rag_record(
            workspace.channel_rag_dir,
            parent_record,
            kind="miho-discord-channel-rag",
        )
