"""Discord thread context for life record tools."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import Any

from gateway.discord_workspace import ensure_workspace
from gateway.discord_workspace_paths import clean_component, discord_root
from miho_constants import get_miho_home


GUILD_ID: ContextVar[str] = ContextVar("life_record_guild_id", default="")
CHANNEL_ID: ContextVar[str] = ContextVar("life_record_channel_id", default="")
CHANNEL_NAME: ContextVar[str] = ContextVar("life_record_channel_name", default="")
THREAD_ID: ContextVar[str] = ContextVar("life_record_thread_id", default="")
THREAD_NAME: ContextVar[str] = ContextVar("life_record_thread_name", default="")
USER_TEXT: ContextVar[str] = ContextVar("life_record_user_text", default="")

_LAST_USER_TEXT_BY_CHAT: dict[str, str] = {}


def capture_gateway_context(event: Any = None) -> None:
    source = getattr(event, "source", None)
    parent_chat_id = str(getattr(source, "parent_chat_id", "") or "")
    chat_id = str(getattr(source, "chat_id", "") or "")
    thread_id = str(getattr(source, "thread_id", "") or "")
    if parent_chat_id and not thread_id:
        thread_id = chat_id
    GUILD_ID.set(str(getattr(source, "guild_id", "") or ""))
    CHANNEL_ID.set(parent_chat_id or chat_id)
    CHANNEL_NAME.set(str(getattr(source, "parent_chat_name", "") or parent_chat_id or chat_id))
    THREAD_ID.set(thread_id)
    THREAD_NAME.set(str(getattr(source, "chat_name", "") or thread_id))
    text = str(getattr(event, "text", "") or "")
    USER_TEXT.set(text)
    for key in {chat_id, thread_id}:
        if key:
            _LAST_USER_TEXT_BY_CHAT[key] = text


def current_life_record_dir() -> Path:
    channel_id = CHANNEL_ID.get().strip()
    if channel_id:
        workspace = ensure_workspace(
            guild_id=GUILD_ID.get(),
            channel_id=channel_id,
            channel_name=CHANNEL_NAME.get(),
            thread_id=THREAD_ID.get(),
            thread_name=THREAD_NAME.get(),
        )
        return workspace.active_dir / "life_records"
    session_dir = _session_life_record_dir()
    if session_dir:
        return session_dir
    return get_miho_home() / "life_records" / "local"


def user_requested_life_record_confirm() -> bool:
    text = USER_TEXT.get().strip() or _last_session_text()
    compact = " ".join(text.split())
    if not compact:
        return False
    confirm_markers = ("검수 확정", "원본 확인", "원본 대조", "확정해", "확정해줘", "중앙DB", "중앙 DB", "승격")
    return any(marker in compact for marker in confirm_markers)


def _last_session_text() -> str:
    try:
        from gateway.session_context import get_session_env
    except Exception:
        return ""
    for key in (get_session_env("MIHO_SESSION_THREAD_ID"), get_session_env("MIHO_SESSION_CHAT_ID")):
        text = _LAST_USER_TEXT_BY_CHAT.get(str(key or ""))
        if text:
            return text
    return ""


def _session_life_record_dir() -> Path | None:
    try:
        from gateway.session_context import get_session_env
    except Exception:
        return None
    if get_session_env("MIHO_SESSION_PLATFORM") != "discord":
        return None
    for ident in (get_session_env("MIHO_SESSION_THREAD_ID"), get_session_env("MIHO_SESSION_CHAT_ID")):
        found = _find_discord_thread_dir(ident)
        if found:
            return found / "life_records"
    return None


def _find_discord_thread_dir(ident: Any) -> Path | None:
    clean_id = clean_component(ident, "")
    if not clean_id:
        return None
    root = discord_root() / "guilds"
    if not root.exists():
        return None
    suffix = "__" + clean_id
    matches = [p for p in root.glob("*/channels/*/threads/*") if p.is_dir() and p.name.endswith(suffix)]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)
