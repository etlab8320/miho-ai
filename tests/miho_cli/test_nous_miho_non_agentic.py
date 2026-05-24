"""Tests for the Nous-Miho-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"miho"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``miho-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "miho" tag namespace.

``is_nous_miho_non_agentic`` should only match the actual Nous Research
Miho-3 / Miho-4 chat family.
"""

from __future__ import annotations

import pytest

from miho_cli.model_switch import (
    _MIHO_MODEL_WARNING,
    _check_miho_model_warning,
    is_nous_miho_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "NousResearch/Miho-3-Llama-3.1-70B",
        "NousResearch/Miho-3-Llama-3.1-405B",
        "miho-3",
        "Miho-3",
        "miho-4",
        "miho-4-405b",
        "miho_4_70b",
        "openrouter/miho3:70b",
        "openrouter/nousresearch/miho-4-405b",
        "NousResearch/Miho3",
        "miho-3.1",
    ],
)
def test_matches_real_nous_miho_chat_models(model_name: str) -> None:
    assert is_nous_miho_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous Miho 3/4"
    )
    assert _check_miho_model_warning(model_name) == _MIHO_MODEL_WARNING


@pytest.mark.parametrize(
    "model_name",
    [
        # Kyle's local Modelfile — qwen3:14b under a custom tag
        "miho-brain:qwen3-14b-ctx16k",
        "miho-brain:qwen3-14b-ctx32k",
        "miho-honcho:qwen3-8b-ctx8k",
        # Plain unrelated models
        "qwen3:14b",
        "qwen3-coder:30b",
        "qwen2.5:14b",
        "claude-opus-4-6",
        "anthropic/claude-sonnet-4.5",
        "gpt-5",
        "openai/gpt-4o",
        "google/gemini-2.5-flash",
        "deepseek-chat",
        # Non-chat Miho models we don't warn about
        "miho-llm-2",
        "miho2-pro",
        "nous-miho-2-mistral",
        # Edge cases
        "",
        "miho",  # bare "miho" isn't the 3/4 family
        "miho-brain",
        "brain-miho-3-impostor",  # "3" not preceded by /: boundary
    ],
)
def test_does_not_match_unrelated_models(model_name: str) -> None:
    assert not is_nous_miho_non_agentic(model_name), (
        f"expected {model_name!r} NOT to be flagged as Nous Miho 3/4"
    )
    assert _check_miho_model_warning(model_name) == ""


def test_none_like_inputs_are_safe() -> None:
    assert is_nous_miho_non_agentic("") is False
    # Defensive: the helper shouldn't crash on None-ish falsy input either.
    assert _check_miho_model_warning("") == ""
