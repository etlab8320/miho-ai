import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import Platform
from gateway.platforms.base import SendResult
from tools import slash_confirm


def _make_runner(adapter):
    runner = SimpleNamespace()
    runner.adapters = {Platform.DISCORD: adapter}
    runner.config = SimpleNamespace(
        get_home_channel=lambda platform: SimpleNamespace(
            chat_id="12345",
            thread_id="67890",
        ) if platform is Platform.DISCORD else None,
    )
    runner._slash_confirm_counter = itertools.count(1)
    runner._session_key_for_source = lambda source: (
        f"{source.platform.value}:{source.chat_id}:{source.thread_id}"
    )
    runner._handle_update_command = AsyncMock(return_value="업데이트를 시작했어.")
    return runner


@pytest.mark.asyncio
async def test_discord_update_available_sends_button_and_runs_update(
    tmp_path, monkeypatch,
):
    from gateway import update_notifier

    adapter = SimpleNamespace(
        send_update_available=AsyncMock(return_value=SendResult(success=True)),
    )
    runner = _make_runner(adapter)

    monkeypatch.setattr(update_notifier, "get_miho_home", lambda: tmp_path)
    monkeypatch.setattr(update_notifier, "check_for_updates", lambda: 2)
    monkeypatch.setattr(
        update_notifier,
        "get_git_banner_state",
        lambda: {"local": "local1234", "upstream": "remote5678"},
    )

    sent = await update_notifier.maybe_notify_discord_update_available(runner)

    assert sent is True
    adapter.send_update_available.assert_awaited_once()
    pending = slash_confirm.get_pending("discord:12345:67890")
    assert pending is not None

    result = await slash_confirm.resolve(
        "discord:12345:67890",
        pending["confirm_id"],
        "once",
    )

    assert result == "업데이트를 시작했어."
    runner._handle_update_command.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_update_available_dedupes_same_revision(tmp_path, monkeypatch):
    from gateway import update_notifier

    adapter = SimpleNamespace(
        send_update_available=AsyncMock(return_value=SendResult(success=True)),
    )
    runner = _make_runner(adapter)

    monkeypatch.setattr(update_notifier, "get_miho_home", lambda: tmp_path)
    monkeypatch.setattr(update_notifier, "check_for_updates", lambda: 1)
    monkeypatch.setattr(
        update_notifier,
        "get_git_banner_state",
        lambda: {"local": "local1234", "upstream": "remote5678"},
    )

    assert await update_notifier.maybe_notify_discord_update_available(runner) is True
    assert await update_notifier.maybe_notify_discord_update_available(runner) is False
    assert adapter.send_update_available.await_count == 1


@pytest.mark.asyncio
async def test_discord_update_available_skips_when_no_update(tmp_path, monkeypatch):
    from gateway import update_notifier

    adapter = MagicMock()
    runner = _make_runner(adapter)

    monkeypatch.setattr(update_notifier, "get_miho_home", lambda: tmp_path)
    monkeypatch.setattr(update_notifier, "check_for_updates", lambda: 0)

    assert await update_notifier.maybe_notify_discord_update_available(runner) is False
    adapter.send_update_available.assert_not_called()
