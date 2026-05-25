"""Archive deleted Discord channel/thread workspace directories."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from gateway.discord_workspace_paths import (
    child_by_id,
    clean_component,
    discord_root,
    stamp,
    utc_now,
    write_manifest,
)


def _archive_destination(path: Path, category: str) -> Path:
    root = discord_root()
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = Path(path.name)
    dest = root / "archive" / "deleted" / category / stamp() / relative
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
    write_manifest(dest / "archive.json", metadata)
    return dest


def archive_workspace_for_channel(channel: Any) -> Path | None:
    channel_id = getattr(channel, "id", None)
    if channel_id is None:
        return None
    guild = getattr(channel, "guild", None)
    guild_dir = discord_root() / "guilds" / clean_component(
        getattr(guild, "id", None),
        "direct",
    )
    channel_dir = child_by_id(guild_dir / "channels", channel_id)
    if channel_dir is None:
        return None
    return _archive_path(
        channel_dir,
        {
            "archived_at": utc_now(),
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
    guild_dir = discord_root() / "guilds" / clean_component(
        getattr(guild, "id", None),
        "direct",
    )
    channels_dir = guild_dir / "channels"
    channel_candidates: list[Path] = []
    parent_id = getattr(parent, "id", None) or getattr(thread, "parent_id", None)
    if parent_id:
        found = child_by_id(channels_dir, parent_id)
        if found is not None:
            channel_candidates.append(found)
    if channels_dir.exists():
        channel_candidates.extend(
            child for child in channels_dir.iterdir()
            if child.is_dir() and child not in channel_candidates
        )
    for channel_dir in channel_candidates:
        thread_dir = child_by_id(channel_dir / "threads", thread_id)
        if thread_dir is not None:
            return _archive_path(
                thread_dir,
                {
                    "archived_at": utc_now(),
                    "reason": "discord_thread_deleted",
                    "guild_id": str(getattr(guild, "id", "") or ""),
                    "parent_channel_id": str(parent_id or ""),
                    "thread_id": str(thread_id),
                    "thread_name": str(getattr(thread, "name", "") or ""),
                },
                category="threads",
            )
    return None
