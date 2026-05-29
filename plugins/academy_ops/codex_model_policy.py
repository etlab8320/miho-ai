"""Codex model role policy for fast academy operations."""

from __future__ import annotations

import os


CODEX_PROVIDER = "openai-codex"
ROUTER_MODEL = "gpt-5.4-mini"
COMMENTARY_MODEL = "gpt-5.4-mini"
SESSION_MODEL = "gpt-5.4-mini"
CRITICAL_MODEL = "gpt-5.4"
DEEP_MODEL = "gpt-5.5"


def codex_provider() -> str:
    return _env("MIHO_ACADEMY_CODEX_PROVIDER", CODEX_PROVIDER)


def router_model() -> str:
    return _env("MIHO_ACADEMY_CODEX_ROUTER_MODEL", ROUTER_MODEL)


def commentary_model() -> str:
    return _env("MIHO_ACADEMY_CODEX_COMMENTARY_MODEL", COMMENTARY_MODEL)


def session_model() -> str:
    return _env("MIHO_ACADEMY_CODEX_SESSION_MODEL", SESSION_MODEL)


def critical_model() -> str:
    return _env("MIHO_ACADEMY_CODEX_CRITICAL_MODEL", CRITICAL_MODEL)


def deep_model() -> str:
    return _env("MIHO_ACADEMY_CODEX_DEEP_MODEL", DEEP_MODEL)


def router_fallback_models() -> tuple[str, ...]:
    return _fallbacks(
        "MIHO_ACADEMY_CODEX_ROUTER_FALLBACK_MODELS",
        (commentary_model(), critical_model(), "gpt-5.2"),
    )


def commentary_fallback_models() -> tuple[str, ...]:
    return _fallbacks(
        "MIHO_ACADEMY_CODEX_COMMENTARY_FALLBACK_MODELS",
        (critical_model(), "gpt-5.2"),
    )


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _fallbacks(name: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return tuple(model for model in defaults if model)
    return tuple(model.strip() for model in raw.split(",") if model.strip())
