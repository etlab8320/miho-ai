"""Tests for academy response synthesis and short commentary."""

from __future__ import annotations

import asyncio

import pytest

import plugins.academy_ops.response_commentary as response_commentary
import plugins.academy_ops.response_synthesis as response_synthesis
from plugins.academy_ops.response_commentary import append_summary_comment_or_fallback
from plugins.academy_ops.response_synthesis import synthesize_or_fallback, synthesis_messages


def test_synthesis_prompt_uses_miho_persona_capsule() -> None:
    messages = synthesis_messages("학생A 5월 출석 조회", {"message": "조회 결과"})

    system = messages[0]["content"]
    assert "현재 사용자에게 말하듯" in system
    assert "존대" in system
    assert "숫자, 날짜, 학생명" in system
    assert "upcoming" in system
    assert "미체크나 문제로 보지 마" in system


@pytest.mark.asyncio
async def test_polite_synthesis_falls_back_without_retry(monkeypatch) -> None:
    calls = 0

    async def polite_synthesis(_: str, __: dict) -> str:
        nonlocal calls
        calls += 1
        return "학생A 5월 출석은 출석 9회예요."

    monkeypatch.setattr(response_synthesis, "synthesize_response", polite_synthesis)

    result = await synthesize_or_fallback(
        "학생A 5월 출석 조회",
        {"ok": True},
        "학생A 5월 출석: 출석 9회, 지각 1회, 결석 1회.",
    )

    assert calls == 1
    assert result == "학생A 5월 출석: 출석 9회, 지각 1회, 결석 1회."


@pytest.mark.asyncio
async def test_summary_focus_appends_optional_comment(monkeypatch) -> None:
    async def summary_comment(_: str, __: dict) -> str:
        return "미체크 날짜만 한 번 확인하면 돼."

    monkeypatch.setattr(response_commentary, "synthesize_summary_comment", summary_comment)

    result = await append_summary_comment_or_fallback(
        "학생A 5월 출석 조회",
        {"ok": True, "summary": {"unchecked": 1}},
        "학생A 5월 출석: 출석 9회, 지각 0회, 결석 0회, 미체크 1회.",
    )

    assert result.endswith("\n미체크 날짜만 한 번 확인하면 돼.")


@pytest.mark.asyncio
async def test_summary_focus_comment_timeout_keeps_fast_fallback(monkeypatch) -> None:
    async def slow_summary_comment(_: str, __: dict) -> str:
        await asyncio.sleep(0.05)
        return "늦게 온 코멘트"

    monkeypatch.setattr(response_commentary, "synthesize_summary_comment", slow_summary_comment)
    monkeypatch.setattr(response_commentary, "SUMMARY_COMMENT_TIMEOUT_SECONDS", 0.01)

    result = await append_summary_comment_or_fallback(
        "학생A 5월 출석 조회",
        {"ok": True, "summary": {"unchecked": 1}},
        "학생A 5월 출석: 출석 9회, 지각 0회, 결석 0회, 미체크 1회.",
    )

    assert result == "학생A 5월 출석: 출석 9회, 지각 0회, 결석 0회, 미체크 1회."
