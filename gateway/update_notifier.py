"""Gateway update-available notices for operator chat surfaces."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from miho_cli import __version__ as VERSION
from miho_cli.banner_update import check_for_updates, get_git_banner_state
from miho_constants import get_miho_home

logger = logging.getLogger(__name__)

_STAMP_FILENAME = ".update_available_notice.json"
_DEFAULT_INTERVAL_SECONDS = 6 * 3600


def _notices_enabled() -> bool:
    if os.getenv("MIHO_DISABLE_UPDATE_NOTICES", "").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        return False
    raw = os.getenv("MIHO_UPDATE_NOTICES", "").strip().lower()
    if not raw:
        return True
    return raw in {"1", "true", "yes", "on"}


def _stamp_key(*, chat_id: str, thread_id: str, behind: int) -> dict[str, Any]:
    state = get_git_banner_state() or {}
    return {
        "platform": "discord",
        "chat_id": chat_id,
        "thread_id": thread_id,
        "version": VERSION,
        "local": state.get("local", ""),
        "upstream": state.get("upstream", ""),
        "behind": behind,
    }


def _already_notified(key: dict[str, Any]) -> bool:
    path = get_miho_home() / _STAMP_FILENAME
    try:
        return json.loads(path.read_text()) == key
    except (OSError, json.JSONDecodeError):
        return False


def _write_notified(key: dict[str, Any]) -> None:
    path = get_miho_home() / _STAMP_FILENAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(key, ensure_ascii=False))
        tmp.replace(path)
    except OSError as exc:
        logger.debug("Failed to write update notice stamp: %s", exc)


def _update_in_progress() -> bool:
    home = get_miho_home()
    return any(
        (home / name).exists()
        for name in (".update_pending.json", ".update_pending.claimed.json")
    )


async def maybe_notify_discord_update_available(runner: Any) -> bool:
    """Send one Discord home-channel notice when the install is behind."""
    if not _notices_enabled() or _update_in_progress():
        return False

    adapter = runner.adapters.get(Platform.DISCORD)
    if adapter is None:
        return False

    home = runner.config.get_home_channel(Platform.DISCORD)
    if not home or not getattr(home, "chat_id", None):
        return False

    try:
        behind = await asyncio.to_thread(check_for_updates)
    except Exception as exc:
        logger.debug("Update availability check failed: %s", exc)
        return False
    if behind is None or behind <= 0:
        return False

    chat_id = str(home.chat_id)
    thread_id = str(getattr(home, "thread_id", "") or "")
    key = _stamp_key(chat_id=chat_id, thread_id=thread_id, behind=int(behind))
    if _already_notified(key):
        return False

    source = SessionSource(
        platform=Platform.DISCORD,
        user_id="system",
        chat_id=chat_id,
        user_name="Miho",
        thread_id=thread_id or None,
    )
    event = MessageEvent(text="/update", source=source)
    session_key = runner._session_key_for_source(source)

    counter = getattr(runner, "_slash_confirm_counter", None)
    if counter is None:
        import itertools
        counter = itertools.count(1)
        runner._slash_confirm_counter = counter
    confirm_id = f"update-{next(counter)}"

    async def _on_confirm(choice: str) -> str:
        if choice == "cancel":
            return "업데이트는 나중에 할게."
        return await runner._handle_update_command(event)

    from tools import slash_confirm
    slash_confirm.register(session_key, confirm_id, "update", _on_confirm)

    metadata = {"thread_id": thread_id} if thread_id else None
    sender = getattr(adapter, "send_update_available", None)
    try:
        if callable(sender):
            result = await sender(
                chat_id,
                current_version=VERSION,
                behind=int(behind),
                session_key=session_key,
                confirm_id=confirm_id,
                metadata=metadata,
            )
        else:
            msg = (
                f"업데이트가 있어. 현재 버전은 `{VERSION}`이고 "
                f"`origin/main`보다 {int(behind)}개 커밋 뒤에 있어.\n"
                "Discord 버튼을 지원하지 않는 어댑터라서 `/update`를 직접 보내면 돼."
            )
            result = await adapter.send(chat_id, msg, metadata=metadata)
    except Exception as exc:
        slash_confirm.clear(session_key)
        logger.debug("Failed to send update-available notice: %s", exc)
        return False

    if result is not None and getattr(result, "success", True) is False:
        slash_confirm.clear(session_key)
        logger.debug(
            "Update-available notice failed: %s",
            getattr(result, "error", "send returned success=False"),
        )
        return False

    _write_notified(key)
    return True


async def _update_notice_loop(runner: Any, interval_seconds: float) -> None:
    await asyncio.sleep(2.0)
    while getattr(runner, "_running", True):
        try:
            await maybe_notify_discord_update_available(runner)
        except Exception as exc:
            logger.debug("Update-available notice loop failed: %s", exc)
        await asyncio.sleep(interval_seconds)


def schedule_update_available_notifications(
    runner: Any,
    *,
    interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Start one best-effort update-available background watcher."""
    existing = getattr(runner, "_update_available_notice_task", None)
    if existing and not existing.done():
        return
    try:
        runner._update_available_notice_task = asyncio.create_task(
            _update_notice_loop(runner, interval_seconds)
        )
    except RuntimeError:
        logger.debug("Skipping update-available watcher: no running event loop")
