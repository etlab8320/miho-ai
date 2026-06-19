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
