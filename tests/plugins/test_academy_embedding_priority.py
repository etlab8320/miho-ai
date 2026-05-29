"""Embedding-first guarantee for login / output-format intent routing.

Per the owner's permanent rule, keyword markers in login_preflight /
route_overrides are an EMERGENCY FALLBACK only. These tests pin that contract:
when semantic_intents.classify returns a decision it always wins, and the
keyword path runs only when classify returns None (no provider / ambiguous).
"""

from __future__ import annotations

from plugins.academy_ops import login_preflight, route_overrides, semantic_intents


def _clear_caches() -> None:
    login_preflight._last_login.update(text=None, label=None, hit=False)
    route_overrides._last_output.update(text=None, label=None, hit=False)


def test_login_embedding_decision_overrides_keywords(monkeypatch) -> None:
    _clear_caches()
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: "login_request")
    # No login keywords at all, but semantic says login_request -> True.
    assert login_preflight.is_academy_login_request("안녕 미호야") is True

    _clear_caches()
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: "none")
    # Strong login keywords, but semantic says none -> keywords must NOT win.
    assert login_preflight.is_academy_login_request("파카 로그인 연결해줘") is False


def test_login_keyword_fallback_only_when_semantic_none(monkeypatch) -> None:
    _clear_caches()
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: None)
    assert login_preflight.is_academy_login_request("파카 로그인 연결해줘") is True
    _clear_caches()
    assert login_preflight.is_academy_login_request("안녕 미호야") is False


def test_output_embedding_decision_overrides_keywords(monkeypatch) -> None:
    _clear_caches()
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: "image")
    assert (
        route_overrides.forced_tool_for_output_request(
            "출결 내역 알려줘", "academy_student_attendance_range"
        )
        == "academy_student_attendance_calendar_image"
    )

    _clear_caches()
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: "none")
    # "이미지" keyword present, but semantic says none -> no forced image tool.
    assert (
        route_overrides.forced_tool_for_output_request(
            "이미지로 보여줘", "academy_student_attendance_range"
        )
        == ""
    )


def test_output_keyword_fallback_only_when_semantic_none(monkeypatch) -> None:
    _clear_caches()
    monkeypatch.setattr(semantic_intents, "classify", lambda *a, **k: None)
    assert (
        route_overrides.forced_tool_for_output_request(
            "이미지로 보여줘", "academy_student_attendance_range"
        )
        == "academy_student_attendance_calendar_image"
    )
