"""Tests for Miho Forge coding-mode guidance."""

from __future__ import annotations

from agent.forge_guidance import FORGE_CODING_GUIDANCE, should_inject_forge_guidance


def test_forge_guidance_injects_for_coding_toolsets():
    assert should_inject_forge_guidance({"terminal", "read_file"}) is True
    assert should_inject_forge_guidance({"patch", "search_files"}) is True
    assert should_inject_forge_guidance({"execute_code"}) is True


def test_forge_guidance_skips_non_coding_toolsets():
    assert should_inject_forge_guidance({"web_search", "memory", "clarify"}) is False
    assert should_inject_forge_guidance(set()) is False


def test_forge_guidance_encodes_one_question_preflight():
    assert "Forge Preflight" in FORGE_CODING_GUIDANCE
    assert "Ask exactly one question at a time" in FORGE_CODING_GUIDANCE
    assert "Do not send a questionnaire" in FORGE_CODING_GUIDANCE
    assert "non-developer" in FORGE_CODING_GUIDANCE


def test_forge_guidance_encodes_no_midrun_questions_and_quality_loop():
    assert "Forge Run v1" in FORGE_CODING_GUIDANCE
    assert "Forge Run v2" in FORGE_CODING_GUIDANCE
    assert "Forge Run v3" in FORGE_CODING_GUIDANCE
    assert "do not ask mid-run clarification questions" in FORGE_CODING_GUIDANCE
    assert "review the changed code yourself" in FORGE_CODING_GUIDANCE
    assert "skill_curator" in FORGE_CODING_GUIDANCE
