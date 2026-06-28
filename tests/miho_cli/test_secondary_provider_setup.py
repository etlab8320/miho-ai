from __future__ import annotations

import inspect

from miho_cli import setup as setup_mod


def test_setup_model_provider_runs_secondary_section_last():
    source = inspect.getsource(setup_mod.setup_model_provider)

    assert source.rfind("_setup_secondary_provider_fallback") > source.rfind("_setup_tts_provider")
    assert source.rfind("_setup_secondary_provider_fallback") > source.rfind("Vision & Image Analysis")


def test_save_secondary_fallback_writes_single_llm_chain():
    config = {"fallback_providers": [{"provider": "old", "model": "old-model"}]}

    setup_mod._save_secondary_fallback(
        config,
        setup_mod._secondary_entry(
            "minimax",
            "MiniMax-M3",
            base_url="https://api.minimax.io/v1",
            key_env="MINIMAX_API_KEY",
        ),
    )

    assert config["fallback_providers"] == [
        {
            "provider": "minimax",
            "model": "MiniMax-M3",
            "base_url": "https://api.minimax.io/v1",
            "key_env": "MINIMAX_API_KEY",
        }
    ]
    assert "secondary_provider" not in config


def test_clear_secondary_fallback_fail_closed_chain():
    config = {"fallback_providers": [{"provider": "minimax", "model": "MiniMax-M3"}]}

    setup_mod._save_secondary_fallback(config, None)

    assert config["fallback_providers"] == []


def test_setup_secondary_minimax_api_key_uses_env_var_not_config_secret(monkeypatch):
    config = {}
    saved_configs = []
    saved_env = []

    monkeypatch.setattr(setup_mod, "print_header", lambda *a, **k: None)
    monkeypatch.setattr(setup_mod, "print_info", lambda *a, **k: None)
    monkeypatch.setattr(setup_mod, "print_success", lambda *a, **k: None)
    monkeypatch.setattr(setup_mod, "prompt_choice", lambda *a, **k: 2)

    prompts = iter([
        "secret-minimax-key",
        "MiniMax-M3",
        "https://api.minimax.io/v1",
    ])
    monkeypatch.setattr(setup_mod, "prompt", lambda *a, **k: next(prompts))
    monkeypatch.setattr(setup_mod, "save_env_value", lambda key, value: saved_env.append((key, value)))
    monkeypatch.setattr(setup_mod, "save_config", lambda cfg: saved_configs.append(dict(cfg)))

    setup_mod._setup_secondary_provider_fallback(config, "openai-codex")

    assert saved_env == [("MINIMAX_API_KEY", "secret-minimax-key")]
    assert config["fallback_providers"] == [
        {
            "provider": "minimax",
            "model": "MiniMax-M3",
            "base_url": "https://api.minimax.io/v1",
            "key_env": "MINIMAX_API_KEY",
        }
    ]
    assert "secret-minimax-key" not in repr(config)
    assert saved_configs[-1] == config
