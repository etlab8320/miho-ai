"""Hybrid-retrieval tuning is named and config-overridable.

The semantic/keyword weights and score thresholds used to be inline magic
numbers in retrieve_rag_context. These tests pin the defaults (so behaviour is
unchanged) and prove the config override path works, matching how the
semantic-intent threshold is configurable.
"""

from __future__ import annotations

import gateway.discord_workspace_vectors as v


def test_default_tuning_matches_constants() -> None:
    assert v._retrieval_tuning() == v._DEFAULT_RETRIEVAL_TUNING
    assert v._DEFAULT_RETRIEVAL_TUNING["semantic_weight"] == 0.65
    assert v._DEFAULT_RETRIEVAL_TUNING["keyword_weight"] == 0.35


def test_keyword_score_respects_weights() -> None:
    # All query terms appear in the text -> full coverage.
    assert v._keyword_score("alpha beta", "alpha beta gamma", 1.0, 0.0) == 1.0
    # Exact match -> full precision.
    assert v._keyword_score("alpha beta", "alpha beta", 0.0, 1.0) == 1.0


def test_config_override_applies(monkeypatch) -> None:
    import miho_cli.config as cfg

    monkeypatch.setattr(
        cfg,
        "load_config",
        lambda: {"discord": {"workspace_rag": {"retrieval": {"semantic_weight": 0.9}}}},
    )
    tuning = v._retrieval_tuning()
    assert tuning["semantic_weight"] == 0.9
    # Unspecified keys keep their defaults.
    assert tuning["keyword_weight"] == 0.35


def test_config_override_ignores_bad_values(monkeypatch) -> None:
    import miho_cli.config as cfg

    monkeypatch.setattr(
        cfg,
        "load_config",
        lambda: {"discord": {"workspace_rag": {"retrieval": {"semantic_weight": "oops"}}}},
    )
    assert v._retrieval_tuning()["semantic_weight"] == 0.65
