"""Tests for the Agent Reach routing tool."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import tools.agent_reach_tool as agent_reach_tool
from tools.registry import registry


def test_status_handles_missing_cli(monkeypatch):
    monkeypatch.delenv(agent_reach_tool.AGENT_REACH_BIN_ENV, raising=False)
    monkeypatch.setattr(agent_reach_tool.shutil, "which", lambda _: None)

    result = json.loads(agent_reach_tool.agent_reach_status_tool({"run_doctor": True}))

    assert result["success"] is True
    assert result["installed"] is False
    assert result["doctor_ran"] is False
    assert "not installed" in result["message"]


def test_status_normalizes_top_level_doctor_json(monkeypatch):
    payload = {
        "youtube": {
            "status": "ok",
            "active_backend": "yt-dlp",
            "tier": 0,
            "backends": ["yt-dlp"],
            "message": "ready",
        },
        "noise": "ignored",
    }

    monkeypatch.setattr(agent_reach_tool.shutil, "which", lambda _: "/usr/bin/agent-reach")
    monkeypatch.setattr(
        agent_reach_tool.subprocess,
        "run",
        lambda *_, **__: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    result = json.loads(agent_reach_tool.agent_reach_status_tool({"run_doctor": True}))

    assert result["installed"] is True
    assert result["doctor_ran"] is True
    assert result["channels"]["youtube"]["status"] == "ok"
    assert result["channels"]["youtube"]["active_backend"] == "yt-dlp"
    assert "noise" not in result["channels"]


def test_status_reports_doctor_timeout(monkeypatch):
    def timeout(*_, **__):
        raise subprocess.TimeoutExpired(cmd=["agent-reach"], timeout=10)

    monkeypatch.setattr(agent_reach_tool.shutil, "which", lambda _: "/usr/bin/agent-reach")
    monkeypatch.setattr(agent_reach_tool.subprocess, "run", timeout)

    result = json.loads(agent_reach_tool.agent_reach_status_tool({"run_doctor": True}))

    assert result["success"] is False
    assert result["doctor_ran"] is True
    assert "timed out" in result["error"]


def test_route_prefers_ok_youtube_backend(monkeypatch):
    monkeypatch.setattr(agent_reach_tool.shutil, "which", lambda _: "/usr/bin/agent-reach")
    monkeypatch.setattr(
        agent_reach_tool,
        "_run_doctor",
        lambda: (
            {"youtube": {"status": "ok", "active_backend": "yt-dlp"}},
            {"youtube": {"status": "ok"}},
            None,
        ),
    )

    result = json.loads(agent_reach_tool.agent_reach_route_tool({
        "request": "https://youtu.be/example video subtitles",
    }))

    assert result["primary_channel"] == "youtube"
    assert result["routes"][0]["channel"] == "youtube"
    assert result["routes"][0]["active_backend"] == "yt-dlp"
    assert result["routes"][0]["setup_needed"] is False


def test_route_detects_github_without_doctor():
    result = json.loads(agent_reach_tool.agent_reach_route_tool({
        "request": "github repo search for agent reach",
        "include_status": False,
    }))

    assert result["primary_channel"] == "github"
    assert result["routes"][0]["channel"] == "github"
    assert result["routes"][0]["status"] == "unknown"


def test_registry_discovers_agent_reach_toolset():
    assert registry.get_entry("agent_reach_status") is not None
    assert registry.get_entry("agent_reach_route") is not None
    assert "agent_reach_status" in registry.get_tool_names_for_toolset("agent_reach")
    assert "agent_reach_route" in registry.get_tool_names_for_toolset("agent_reach")


def test_research_router_requires_llm_mapping():
    result = json.loads(agent_reach_tool.research_router_tool({"request": "search this"}))

    assert result["success"] is False
    assert "llm_intent is required" in result["error"]
    assert result["policy"].startswith("LLM maps")


def test_research_router_prefers_available_agent_reach_public_channel(monkeypatch):
    monkeypatch.setattr(
        agent_reach_tool,
        "_run_doctor",
        lambda: (
            {"github": {"status": "ok", "active_backend": "gh CLI"}},
            {"github": {"status": "ok"}},
            None,
        ),
    )

    result = json.loads(agent_reach_tool.research_router_tool({
        "request": "research github repos for agent-reach",
        "llm_intent": {
            "task_type": "public_research",
            "source_type": "github",
            "desired_output": "search_results",
            "candidate_channels": ["github"],
            "rationale": "GitHub repository research",
        },
    }))

    assert result["decision"] == "planned"
    assert result["selected_backend"] == "agent_reach:github"
    assert result["backend_family"] == "agent_reach"
    assert result["policy"]["llm_mapping_required"] is True
    assert result["policy"]["python_semantic_fallback"] is False


def test_research_router_uses_youtube_specialized_tool_for_summary_card(monkeypatch):
    monkeypatch.setattr(
        agent_reach_tool,
        "_run_doctor",
        lambda: (
            {"youtube": {"status": "ok", "active_backend": "yt-dlp"}},
            {"youtube": {"status": "ok"}},
            None,
        ),
    )

    result = json.loads(agent_reach_tool.research_router_tool({
        "request": "summarize this YouTube video and make a card",
        "llm_intent": {
            "task_type": "video_summary",
            "source_type": "youtube",
            "desired_output": "youtube_summary_card",
            "candidate_channels": ["youtube"],
            "needs_youtube_summary_card": True,
        },
    }))

    assert result["decision"] == "planned"
    assert result["selected_backend"] == "youtube_analyze_video"
    assert result["backend_family"] == "legacy"


def test_research_router_blocks_internal_academy_data():
    result = json.loads(agent_reach_tool.research_router_tool({
        "request": "학생 출결 찾아줘",
        "llm_intent": {
            "task_type": "academy",
            "source_type": "paca",
            "candidate_channels": ["web"],
            "uses_private_or_internal_data": True,
        },
        "run_doctor": False,
    }))

    assert result["decision"] == "blocked_from_agent_reach"
    assert result["backend_family"] == "specialized_internal_tool"
    assert "academy_api_query" in result["specialized_backends"]


def test_research_router_blocks_login_or_write_action():
    result = json.loads(agent_reach_tool.research_router_tool({
        "request": "twitter에 글 올려줘",
        "llm_intent": {
            "task_type": "social_action",
            "source_type": "twitter",
            "candidate_channels": ["twitter"],
            "may_write": True,
        },
        "run_doctor": False,
    }))

    assert result["decision"] == "blocked"
    assert result["selected_backend"] is None


def test_registry_discovers_research_router():
    assert registry.get_entry("research_router") is not None
    assert "research_router" in registry.get_tool_names_for_toolset("web")
