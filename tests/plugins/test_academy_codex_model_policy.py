"""Tests for academy Codex role-based model policy."""

from __future__ import annotations

from plugins.academy_ops import codex_model_policy


def test_codex_policy_defaults_split_fast_and_accurate_roles(monkeypatch) -> None:
    for name in (
        "MIHO_ACADEMY_CODEX_PROVIDER",
        "MIHO_ACADEMY_CODEX_ROUTER_MODEL",
        "MIHO_ACADEMY_CODEX_COMMENTARY_MODEL",
        "MIHO_ACADEMY_CODEX_SESSION_MODEL",
        "MIHO_ACADEMY_CODEX_CRITICAL_MODEL",
        "MIHO_ACADEMY_CODEX_ROUTER_FALLBACK_MODELS",
        "MIHO_ACADEMY_CODEX_COMMENTARY_FALLBACK_MODELS",
    ):
        monkeypatch.delenv(name, raising=False)

    assert codex_model_policy.codex_provider() == "openai-codex"
    assert codex_model_policy.router_model() == "gpt-5.3-codex-spark"
    assert codex_model_policy.commentary_model() == "gpt-5.4-mini"
    assert codex_model_policy.session_model() == "gpt-5.4-mini"
    assert codex_model_policy.critical_model() == "gpt-5.4"
    assert codex_model_policy.deep_model() == "gpt-5.5"
    assert codex_model_policy.router_fallback_models() == ("gpt-5.4-mini", "gpt-5.4", "gpt-5.2")
    assert codex_model_policy.commentary_fallback_models() == (
        "gpt-5.3-codex-spark",
        "gpt-5.4",
        "gpt-5.2",
    )


def test_codex_policy_allows_operator_overrides(monkeypatch) -> None:
    monkeypatch.setenv("MIHO_ACADEMY_CODEX_ROUTER_MODEL", "custom-router")
    monkeypatch.setenv("MIHO_ACADEMY_CODEX_COMMENTARY_MODEL", "custom-commentary")
    monkeypatch.setenv("MIHO_ACADEMY_CODEX_ROUTER_FALLBACK_MODELS", "a, b ,, c")

    assert codex_model_policy.router_model() == "custom-router"
    assert codex_model_policy.commentary_model() == "custom-commentary"
    assert codex_model_policy.router_fallback_models() == ("a", "b", "c")
