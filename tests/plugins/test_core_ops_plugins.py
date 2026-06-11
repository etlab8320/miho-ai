"""Core Miho operations plugins should work on fresh installs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from miho_cli.plugins import PluginManager, get_plugin_auxiliary_tasks


def test_academy_ops_loads_without_user_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    manager = PluginManager()
    manager.discover_and_load()

    loaded = manager._plugins["academy_ops"]
    assert loaded.enabled
    assert "pre_gateway_dispatch" in loaded.hooks_registered
    assert "academy" in loaded.commands_registered


def test_decision_twin_loads_without_user_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    manager = PluginManager()
    manager.discover_and_load()

    loaded = manager._plugins["decision_twin"]
    assert loaded.enabled
    callbacks = manager._hooks["pre_gateway_dispatch"]
    assert any(callback.__module__.endswith("decision_twin") for callback in callbacks)
    assert any(task["key"] == "miho_decision_twin" for task in get_plugin_auxiliary_tasks())


def test_youtube_ops_does_not_load_without_user_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    manager = PluginManager()
    manager.discover_and_load()

    loaded = manager._plugins["youtube_ops"]
    assert not loaded.enabled
    assert loaded.error.startswith("not enabled in config")


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
    # semantic이 login_request를 반환하도록 설정 (embedding 없는 CI 환경 대응)
    from plugins.academy_ops import login_preflight, semantic_intents
    from plugins.academy_ops.gateway_dispatch import _academy_pre_gateway_dispatch

    login_preflight._last_login.update(text=None, label=None, hit=False)
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: "login_request")
    monkeypatch.setattr("plugins.academy_ops.gateway_dispatch.refresh_remote_pending_logins", lambda: 0)
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

    result = await _academy_pre_gateway_dispatch(event=event, gateway=gateway)
    login_preflight._last_login.update(text=None, label=None, hit=False)

    assert result.get("action") == "respond"
    assert "https://academy-login.etlab.kr/academy/login?state=" in result.get("text", "")
