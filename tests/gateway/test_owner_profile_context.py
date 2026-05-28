"""Tests for selecting relevant owner profile context for Discord prompts."""

from __future__ import annotations

from gateway.owner_profile_context import build_relevant_owner_profile_context
from miho_cli.owner_profile import append_profile_event


def _write_user_profile(root, *entries: str) -> None:
    memories_dir = root / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)
    (memories_dir / "USER.md").write_text("\n§\n".join(entries) + "\n", encoding="utf-8")


def test_owner_profile_context_prefers_matching_user_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    _write_user_profile(
        tmp_path,
        "- 식단/건강: Max는 칼로리와 체중을 날짜별로 분리해서 정리해야 한다.",
        "- 개발: ET는 커밋 전 스모크 테스트를 선호한다.",
    )

    context = build_relevant_owner_profile_context("오늘 먹은 전체 칼로리 계산해줘")

    assert "Relevant Owner Profile" in context
    assert "칼로리와 체중을 날짜별로" in context
    assert "커밋 전 스모크" not in context


def test_owner_profile_context_includes_matching_timeline_event(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    append_profile_event(
        category="health",
        title="Dinner log",
        content="2026-05-28 저녁은 계란미역국과 밥 2/3공기였다.",
        source="test",
    )

    context = build_relevant_owner_profile_context("계란미역국 먹은 날짜 기준으로 정리해줘")

    assert "owner_profile:health" in context
    assert "2026-05-28" in context
    assert "계란미역국" in context


def test_owner_profile_context_is_empty_without_matches_and_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    assert build_relevant_owner_profile_context("아무 저장도 없는 질문") == ""

    _write_user_profile(tmp_path, "- 칼로리 " + ("아주긴내용 " * 100))

    context = build_relevant_owner_profile_context("칼로리 계산", max_chars=240)

    assert len(context) <= 240
    assert "칼로리" in context
