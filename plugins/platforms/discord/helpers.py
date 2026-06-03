from __future__ import annotations

import re
from typing import Optional

from miho_cli.brand import current_brand

VALID_THREAD_AUTO_ARCHIVE_MINUTES = {60, 1440, 4320, 10080}
_DISCORD_COMMAND_SYNC_POLICIES = {"safe", "bulk", "off"}
_DISCORD_COMMAND_SYNC_STATE_SUBDIR = "gateway"
_DISCORD_COMMAND_SYNC_STATE_FILENAME = "discord_command_sync_state.json"
_DISCORD_COMMAND_SYNC_MUTATION_INTERVAL_SECONDS = 4.5
_DISCORD_COMMAND_SYNC_MAX_RATE_LIMIT_SLEEP_SECONDS = 30.0

_DISCORD_CHANNEL_TYPE_PROBE_CACHE: dict[str, bool] = {}


def _clean_discord_id(entry: str) -> str:
    entry = entry.strip()
    if entry.startswith("<@") and entry.endswith(">"):
        entry = entry.lstrip("<@!").rstrip(">")
    if entry.lower().startswith("user:"):
        entry = entry[5:]
    return entry.strip()


def _discord_brand():
    return current_brand()


def _is_unknown_discord_channel_error(error: Exception) -> bool:
    text = str(error)
    return "error code: 10003" in text or "Unknown Channel" in text


def _thread_created_message(thread_name: str) -> str:
    return f"\U0001f9f5 Thread created by {_discord_brand().short_name}: **{thread_name}**"


def _read_dm_role_auth_guild() -> Optional[int]:
    """Return the config.yaml guild ID opted into DM role-based auth."""
    try:
        from miho_cli.config import read_raw_config

        cfg = read_raw_config() or {}
        discord_cfg = cfg.get("discord", {}) or {}
        raw = discord_cfg.get("dm_role_auth_guild")
    except Exception:
        return None
    if raw is None or raw == "":
        return None
    try:
        guild_id = int(raw)
    except (TypeError, ValueError):
        return None
    return guild_id if guild_id > 0 else None


def _remember_channel_is_forum(chat_id: str, is_forum: bool) -> None:
    _DISCORD_CHANNEL_TYPE_PROBE_CACHE[str(chat_id)] = bool(is_forum)


def _probe_is_forum_cached(chat_id: str) -> Optional[bool]:
    return _DISCORD_CHANNEL_TYPE_PROBE_CACHE.get(str(chat_id))


def _derive_forum_thread_name(message: str) -> str:
    first_line = message.strip().split("\n", 1)[0].strip()
    first_line = first_line.lstrip("#").strip()
    if not first_line:
        first_line = "New Post"
    return first_line[:100]


def _standalone_sanitize_error(text) -> str:
    return re.sub(
        r"(Authorization:\s*Bot\s+)\S+",
        r"\1***",
        str(text),
        flags=re.IGNORECASE,
    )


def _clean_discord_user_ids(raw: str) -> list:
    cleaned = []
    for uid in raw.replace(" ", "").split(","):
        uid = _clean_discord_id(uid)
        if uid:
            cleaned.append(uid)
    return cleaned
