from __future__ import annotations

from unittest.mock import MagicMock

from agent import auxiliary_client


def test_configured_auxiliary_fallback_chain_reads_key_env(monkeypatch):
    calls = []
    sentinel_client = MagicMock()

    monkeypatch.setenv("_MIHO_TEST_AUX_FB_KEY", "aux-secret")
    monkeypatch.setattr(
        auxiliary_client,
        "_get_auxiliary_task_config",
        lambda task: {
            "fallback_chain": [
                {
                    "provider": "minimax",
                    "model": "MiniMax-M3",
                    "base_url": "https://api.minimax.io/v1",
                    "key_env": "_MIHO_TEST_AUX_FB_KEY",
                }
            ]
        },
    )

    def fake_resolve(provider, model=None, base_url=None, api_key=None):
        calls.append(
            {
                "provider": provider,
                "model": model,
                "base_url": base_url,
                "api_key": api_key,
            }
        )
        return sentinel_client

    monkeypatch.setattr(auxiliary_client, "_resolve_single_provider", fake_resolve)

    client, model, label = auxiliary_client._try_configured_fallback_chain(
        "test_task",
        "openai-codex",
        reason="primary failed",
    )

    assert client is sentinel_client
    assert model == "MiniMax-M3"
    assert label == "fallback_chain[0](minimax)"
    assert calls == [
        {
            "provider": "minimax",
            "model": "MiniMax-M3",
            "base_url": "https://api.minimax.io/v1",
            "api_key": "aux-secret",
        }
    ]


def test_configured_auxiliary_fallback_chain_supports_api_key_env_alias(monkeypatch):
    calls = []
    monkeypatch.setenv("_MIHO_TEST_AUX_FB_KEY_ALIAS", "alias-secret")
    monkeypatch.setattr(
        auxiliary_client,
        "_get_auxiliary_task_config",
        lambda task: {
            "fallback_chain": [
                {
                    "provider": "openrouter",
                    "model": "anthropic/claude-sonnet-4.6",
                    "api_key_env": "_MIHO_TEST_AUX_FB_KEY_ALIAS",
                }
            ]
        },
    )
    monkeypatch.setattr(
        auxiliary_client,
        "_resolve_single_provider",
        lambda provider, model=None, base_url=None, api_key=None: calls.append(api_key) or MagicMock(),
    )

    client, _, _ = auxiliary_client._try_configured_fallback_chain(
        "test_task",
        "minimax",
    )

    assert client is not None
    assert calls == ["alias-secret"]
