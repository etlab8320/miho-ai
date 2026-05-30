"""Tests for embedding-based academy intent routing and keyword fallback."""

from __future__ import annotations

import math

import pytest

from plugins.academy_ops import login_preflight, route_overrides, semantic_intents


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    monkeypatch.setenv("MIHO_ACADEMY_SEMANTIC_ROUTING", "1")
    semantic_intents._anchor_cache.clear()
    login_preflight._last_login.update(text=None, label=None, hit=False)
    route_overrides._last_output.update(text=None, label=None, hit=False)
    yield
    semantic_intents._anchor_cache.clear()


def _unit(vec):
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


# --- classify() core behaviour -------------------------------------------------

_INTENTS = {"a": ("alpha one", "alpha two"), "b": ("beta one",), "none": ("noise",)}
_VECS = {
    "alpha one": [1.0, 0.0, 0.0],
    "alpha two": [1.0, 0.0, 0.0],
    "alpha query": [1.0, 0.0, 0.0],
    "beta one": [0.0, 1.0, 0.0],
    "beta query": [0.0, 1.0, 0.0],
    "noise": [0.0, 0.0, 1.0],
    "noise query": [0.0, 0.0, 1.0],
    "ambiguous": [1.0, 1.0, 1.0],
}


def _semantic_embed(text, input_type):
    return _unit(_VECS.get(text, [0.0, 0.0, 1.0])), "voyage-test"


def _localhash_embed(text, input_type):
    return _unit(_VECS.get(text, [0.0, 0.0, 1.0])), "local-hash-v1"


def _openai_embed(text, input_type):
    # embed_text returns the model name (not "openai") for the OpenAI provider.
    return _unit(_VECS.get(text, [0.0, 0.0, 1.0])), "text-embedding-3-small"


def test_classify_returns_confident_label(monkeypatch):
    monkeypatch.setattr(semantic_intents, "_embed", _semantic_embed)
    assert semantic_intents.classify("alpha query", "grp", _INTENTS) == "a"
    assert semantic_intents.classify("beta query", "grp", _INTENTS) == "b"


def test_classify_returns_negative_label_for_unrelated(monkeypatch):
    monkeypatch.setattr(semantic_intents, "_embed", _semantic_embed)
    assert semantic_intents.classify("noise query", "grp", _INTENTS) == "none"


def test_classify_abstains_below_threshold(monkeypatch):
    monkeypatch.setattr(semantic_intents, "_embed", _semantic_embed)
    # "ambiguous" is equidistant (~0.577) from every anchor → below 0.9.
    assert semantic_intents.classify("ambiguous", "grp", _INTENTS, threshold=0.9) is None


def test_classify_abstains_on_local_hash(monkeypatch):
    monkeypatch.setattr(semantic_intents, "_embed", _localhash_embed)
    assert semantic_intents.classify("alpha query", "grp", _INTENTS) is None


def test_classify_accepts_openai_model_method(monkeypatch):
    # Provider-agnostic: any non-local-hash method (e.g. an OpenAI model name)
    # is treated as semantic.
    monkeypatch.setattr(semantic_intents, "_embed", _openai_embed)
    assert semantic_intents.classify("alpha query", "grp", _INTENTS) == "a"


def test_classify_abstains_when_disabled(monkeypatch):
    monkeypatch.setenv("MIHO_ACADEMY_SEMANTIC_ROUTING", "0")
    monkeypatch.setattr(semantic_intents, "_embed", _semantic_embed)
    assert semantic_intents.classify("alpha query", "grp", _INTENTS) is None


# --- negative-margin gate (e5 cosine-compression guard) ------------------------

# e5 packs every Korean sentence into 0.80-0.94, so a positive label can "win"
# while sitting almost on top of the negative anchor. These anchors reproduce
# that: "narrow" beats none by ~0.013 (a false positive), "clear" by ~0.10.
_MARGIN_VECS = {
    "m_alpha": [1.0, 0.0],
    "m_noise": [0.9, 0.436],  # |·|≈1, ~0.9 cosine to m_alpha (anchors sit close)
    "m_narrow_query": [1.0, 0.2],  # alpha≈0.981, none≈0.968 → margin ~0.013
    "m_clear_query": [1.0, 0.0],  # alpha=1.0, none=0.9 → margin ~0.10
}
_MARGIN_INTENTS = {"a": ("m_alpha",), "none": ("m_noise",)}


def _margin_embed(text, input_type):
    return _unit(_MARGIN_VECS.get(text, [0.0, 1.0])), "voyage-test"


def test_classify_margin_abstains_when_close_to_negative(monkeypatch):
    monkeypatch.setattr(semantic_intents, "_embed", _margin_embed)
    # Positive wins but barely beats the negative anchor → abstain (False positive).
    assert semantic_intents.classify(
        "m_narrow_query", "mgrp", _MARGIN_INTENTS, negative_label="none", min_margin=0.04
    ) is None


def test_classify_margin_accepts_clear_winner(monkeypatch):
    monkeypatch.setattr(semantic_intents, "_embed", _margin_embed)
    assert semantic_intents.classify(
        "m_clear_query", "mgrp", _MARGIN_INTENTS, negative_label="none", min_margin=0.04
    ) == "a"


def test_classify_margin_default_off_preserves_behaviour(monkeypatch):
    monkeypatch.setattr(semantic_intents, "_embed", _margin_embed)
    # No opt-in (min_margin=0) → gate inactive, prior best-label behaviour intact.
    assert semantic_intents.classify("m_narrow_query", "mgrp", _MARGIN_INTENTS) == "a"


# --- login_preflight mapping ---------------------------------------------------


def test_login_request_uses_semantic_label(monkeypatch):
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: "login_request")
    assert login_preflight.is_academy_login_request("아무거나") is True
    assert login_preflight.is_academy_login_status_request("아무거나") is False


def test_login_status_uses_semantic_label(monkeypatch):
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: "login_status")
    assert login_preflight.is_academy_login_status_request("아무거나") is True
    assert login_preflight.is_academy_login_request("아무거나") is False


def test_login_confident_none_does_not_trigger(monkeypatch):
    # Semantic says "definitely not a login intent" even if keywords would match.
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: "none")
    assert login_preflight.is_academy_login_request("파카 로그인 연결해줘") is False
    assert login_preflight.is_academy_login_status_request("파카 로그인 됐어?") is False


def test_login_abstain_falls_back_to_keywords(monkeypatch):
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: None)
    # Keyword path still works for known phrasings.
    assert login_preflight.is_academy_login_request("파카 로그인 연결해줘") is True
    assert login_preflight.is_academy_login_status_request("파카 로그인되어있어?") is True


# --- route_overrides mapping ---------------------------------------------------


def test_output_image_forces_calendar(monkeypatch):
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: "image")
    assert (
        route_overrides.forced_tool_for_output_request("x", "academy_student_attendance_range")
        == "academy_student_attendance_calendar_image"
    )
    assert route_overrides.should_render_attendance_day_image("x", "academy_attendance_day") is True


def test_output_card_forces_card_image(monkeypatch):
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: "card")
    assert (
        route_overrides.forced_tool_for_output_request("x", "academy_student_summary")
        == "academy_student_card_image"
    )


def test_output_none_does_not_force(monkeypatch):
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: "none")
    assert route_overrides.forced_tool_for_output_request("카드로 줘", "academy_student_summary") == ""
    assert route_overrides.should_render_attendance_day_image("이미지로", "academy_attendance_day") is False


def test_output_abstain_falls_back_to_keywords(monkeypatch):
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: None)
    assert (
        route_overrides.forced_tool_for_output_request("달력 이미지로 보여줘", "academy_student_attendance_range")
        == "academy_student_attendance_calendar_image"
    )
    assert route_overrides.should_render_attendance_day_image("이미지로 보여줘", "academy_attendance_day") is True
