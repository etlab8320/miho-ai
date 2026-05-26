"""Regression tests for gateway /model --global persistence."""

from __future__ import annotations

import yaml
import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource


def _make_runner():
    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    runner._voice_mode = {}
    runner._session_model_overrides = {}
    runner._running_agents = {}
    return runner


def _make_event(text: str) -> MessageEvent:
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=SessionSource(platform=Platform.TELEGRAM, chat_id="12345", chat_type="dm"),
    )


def _fake_switch_result():
    from miho_cli.model_switch import ModelSwitchResult

    return ModelSwitchResult(
        success=True,
        new_model="gpt-5.5",
        target_provider="openrouter",
        provider_changed=True,
        api_key="sk-test",
        base_url="https://openrouter.ai/api/v1",
        api_mode="chat_completions",
        provider_label="OpenRouter",
        is_global=True,
    )


def _setup_isolated_home(tmp_path, monkeypatch, model_yaml_value):
    import gateway.run as gateway_run

    miho_home = tmp_path / ".miho"
    miho_home.mkdir()
    cfg_path = miho_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"model": model_yaml_value, "providers": {}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(gateway_run, "_miho_home", miho_home)
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    monkeypatch.setattr("miho_cli.model_switch.switch_model", lambda **kw: _fake_switch_result())
    monkeypatch.setattr("miho_constants.get_miho_home", lambda: miho_home)
    monkeypatch.setattr("miho_cli.config.get_miho_home", lambda: miho_home)
    return cfg_path


@pytest.mark.asyncio
async def test_model_global_persists_when_config_has_flat_string_model(tmp_path, monkeypatch):
    cfg_path = _setup_isolated_home(tmp_path, monkeypatch, "deepseek-v4-flash")

    result = await _make_runner()._handle_model_command(_make_event("/model gpt-5.5 --global"))

    assert result is not None
    assert "gpt-5.5" in result
    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert isinstance(written["model"], dict)
    assert written["model"]["default"] == "gpt-5.5"
    assert written["model"]["provider"] == "openrouter"
    assert written["model"]["base_url"] == "https://openrouter.ai/api/v1"


@pytest.mark.asyncio
async def test_model_global_persists_when_config_has_missing_model(tmp_path, monkeypatch):
    import gateway.run as gateway_run

    miho_home = tmp_path / ".miho"
    miho_home.mkdir()
    cfg_path = miho_home / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({"providers": {}}), encoding="utf-8")

    monkeypatch.setattr(gateway_run, "_miho_home", miho_home)
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    monkeypatch.setattr("miho_cli.model_switch.switch_model", lambda **kw: _fake_switch_result())
    monkeypatch.setattr("miho_constants.get_miho_home", lambda: miho_home)
    monkeypatch.setattr("miho_cli.config.get_miho_home", lambda: miho_home)

    result = await _make_runner()._handle_model_command(_make_event("/model gpt-5.5 --global"))

    assert result is not None
    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert isinstance(written["model"], dict)
    assert written["model"]["default"] == "gpt-5.5"
    assert written["model"]["provider"] == "openrouter"
