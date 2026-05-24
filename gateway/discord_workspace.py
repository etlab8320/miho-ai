"""Discord workspace storage for Miho gateway context."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home
from utils import atomic_json_write
from gateway.discord_workspace_prompt import build_workspace_prompt
from gateway.discord_workspace_vectors import index_rag_record, retrieve_rag_context


_MAX_CONTEXT_MESSAGES = 12
_MAX_MESSAGE_CHARS = 700


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _clean_component(value: Any, fallback: str) -> str:
    raw = str(value or "").strip() or fallback
    raw = re.sub(r"\s+", "-", raw.lower())
    raw = re.sub(r"[^a-z0-9_.-]+", "-", raw)
    raw = raw.strip(".-")
    return raw[:64] or fallback


def _named_id(name: Any, ident: Any, fallback: str) -> str:
    clean_name = _clean_component(name, fallback)
    clean_id = _clean_component(ident, "unknown")
    return f"{clean_name}__{clean_id}"


def _workspace_child(parent: Path, name: Any, ident: Any, fallback: str) -> Path:
    wanted = _named_id(name, ident, fallback)
    suffix = "__" + _clean_component(ident, "unknown")
    if parent.exists():
        for child in parent.iterdir():
            if child.is_dir() and child.name.endswith(suffix):
                return child
    return parent / wanted


def _child_by_id(parent: Path, ident: Any) -> Path | None:
    suffix = "__" + _clean_component(ident, "unknown")
    if not parent.exists():
        return None
    for child in parent.iterdir():
        if child.is_dir() and child.name.endswith(suffix):
            return child
    return None


def _write_manifest(path: Path, data: dict[str, Any]) -> None:
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            existing = {}
    now = _utc_now()
    merged = {
        **existing,
        **{k: v for k, v in data.items() if v not in (None, "")},
        "updated_at": now,
    }
    if "created_at" not in merged:
        merged["created_at"] = now
    atomic_json_write(path, merged, indent=2)


def _ensure_rag(active_dir: Path, *, kind: str) -> None:
    rag_dir = active_dir / "rag"
    (rag_dir / "documents").mkdir(parents=True, exist_ok=True)
    index_path = rag_dir / "index.json"
    if not index_path.exists():
        atomic_json_write(
            index_path,
            {
                "version": 1,
                "kind": kind,
                "message_count": 0,
                "updated_at": _utc_now(),
            },
            indent=2,
        )
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
    root = get_miho_home() / "discord" / "guilds" / _clean_component(
        guild_id, "direct"
    )
    channel_dir = _workspace_child(root / "channels", channel_name, channel_id, "channel")
    channel_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(
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
        thread_dir = _workspace_child(
            channel_dir / "threads",
            thread_name,
            thread_id,
            "thread",
        )
        thread_dir.mkdir(parents=True, exist_ok=True)
        _write_manifest(
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


def _discord_root() -> Path:
    return get_miho_home() / "discord"


def _archive_destination(path: Path, category: str) -> Path:
    try:
        relative = path.relative_to(_discord_root())
    except ValueError:
        relative = Path(path.name)
    dest = _discord_root() / "archive" / "deleted" / category / _stamp() / relative
    candidate = dest
    counter = 2
    while candidate.exists():
        candidate = dest.with_name(f"{dest.name}-{counter}")
        counter += 1
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def _archive_path(path: Path, metadata: dict[str, Any], *, category: str) -> Path | None:
    if not path.exists():
        return None
    dest = _archive_destination(path, category)
    shutil.move(str(path), str(dest))
    _write_manifest(dest / "archive.json", metadata)
    return dest


def archive_workspace_for_channel(channel: Any) -> Path | None:
    channel_id = getattr(channel, "id", None)
    if channel_id is None:
        return None
    guild = getattr(channel, "guild", None)
    guild_dir = _discord_root() / "guilds" / _clean_component(
        getattr(guild, "id", None),
        "direct",
    )
    channel_dir = _child_by_id(guild_dir / "channels", channel_id)
    if channel_dir is None:
        return None
    return _archive_path(
        channel_dir,
        {
            "archived_at": _utc_now(),
            "reason": "discord_channel_deleted",
            "guild_id": str(getattr(guild, "id", "") or ""),
            "channel_id": str(channel_id),
            "channel_name": str(getattr(channel, "name", "") or ""),
        },
        category="channels",
    )


def archive_workspace_for_thread(thread: Any) -> Path | None:
    thread_id = getattr(thread, "id", None)
    if thread_id is None:
        return None
    parent = getattr(thread, "parent", None)
    guild = getattr(thread, "guild", None) or getattr(parent, "guild", None)
    guild_dir = _discord_root() / "guilds" / _clean_component(
        getattr(guild, "id", None),
        "direct",
    )
    channels_dir = guild_dir / "channels"
    channel_candidates: list[Path] = []
    parent_id = getattr(parent, "id", None) or getattr(thread, "parent_id", None)
    if parent_id:
        found = _child_by_id(channels_dir, parent_id)
        if found is not None:
            channel_candidates.append(found)
    if channels_dir.exists():
        channel_candidates.extend(
            child for child in channels_dir.iterdir()
            if child.is_dir() and child not in channel_candidates
        )
    for channel_dir in channel_candidates:
        thread_dir = _child_by_id(channel_dir / "threads", thread_id)
        if thread_dir is not None:
            return _archive_path(
                thread_dir,
                {
                    "archived_at": _utc_now(),
                    "reason": "discord_thread_deleted",
                    "guild_id": str(getattr(guild, "id", "") or ""),
                    "parent_channel_id": str(parent_id or ""),
                    "thread_id": str(thread_id),
                    "thread_name": str(getattr(thread, "name", "") or ""),
                },
                category="threads",
            )
    return None


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
            "updated_at": _utc_now(),
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
            else str(timestamp or _utc_now())
        ),
        "message_id": str(message_id or getattr(source, "message_id", "") or ""),
        "user_id": str(getattr(source, "user_id", "") or ""),
        "user_name": str(getattr(source, "user_name", "") or ""),
        "role": "user",
        "text": _compact_text(text),
    }
    active_kind = (
        "miho-discord-thread-rag"
        if workspace.thread_dir
        else "miho-discord-channel-rag"
    )
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
            else str(timestamp or _utc_now())
        ),
        "message_id": str(message_id or ""),
        "user_id": "miho",
        "user_name": "Miho",
        "role": "assistant",
        "text": _compact_text(text),
    }
    active_kind = (
        "miho-discord-thread-rag"
        if workspace.thread_dir
        else "miho-discord-channel-rag"
    )
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
