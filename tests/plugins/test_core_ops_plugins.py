"""Core Miho operations plugins should work on fresh installs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from miho_cli.plugins import PluginManager


def test_academy_ops_loads_without_user_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    manager = PluginManager()
    manager.discover_and_load()

    loaded = manager._plugins["academy_ops"]
    assert loaded.enabled
    assert "pre_gateway_dispatch" in loaded.hooks_registered
    assert "academy" in loaded.commands_registered


def test_youtube_ops_loads_without_user_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    manager = PluginManager()
    manager.discover_and_load()

    loaded = manager._plugins["youtube_ops"]
    assert loaded.enabled
    assert "youtube_analyze_video" in loaded.tools_registered
    assert manager._hooks.get("pre_gateway_dispatch")


def test_core_ops_plugins_still_respect_disabled_config(tmp_path, monkeypatch):
    miho_home = tmp_path / "miho_home"
    miho_home.mkdir()
    (miho_home / "config.yaml").write_text(
        "plugins:\n"
        "  disabled:\n"
        "    - academy_ops\n"
        "    - youtube_ops\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MIHO_HOME", str(miho_home))

    manager = PluginManager()
    manager.discover_and_load()

    assert not manager._plugins["academy_ops"].enabled
    assert manager._plugins["academy_ops"].error == "disabled via config"
    assert not manager._plugins["youtube_ops"].enabled
    assert manager._plugins["youtube_ops"].error == "disabled via config"


@pytest.mark.asyncio
async def test_fresh_install_routes_academy_login_before_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    monkeypatch.setenv("MIHO_ACADEMY_AUTH_BASE_URL", "https://academy-login.etlab.kr")
    event = MessageEvent(
        text="파카 로그인하자",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-1",
            chat_id="channel-1",
            guild_id="guild-1",
        ),
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: True)
    manager = PluginManager()
    manager.discover_and_load()

    results = await manager.invoke_hook_async(
        "pre_gateway_dispatch",
        event=event,
        gateway=gateway,
    )

    assert any(
        result.get("action") == "respond"
        and "https://academy-login.etlab.kr/academy/login?state=" in result.get("text", "")
        for result in results
        if isinstance(result, dict)
    )
