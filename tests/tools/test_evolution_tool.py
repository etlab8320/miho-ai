"""Tests for the Miho Evolution OS tool wrapper."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def evolution_tool_env(monkeypatch, tmp_path):
    home = tmp_path / ".miho"
    home.mkdir()
    (home / "skills").mkdir()
    monkeypatch.setenv("MIHO_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    import miho_constants
    importlib.reload(miho_constants)
    from agent import curator_backup, evolution
    importlib.reload(curator_backup)
    importlib.reload(evolution)
    import tools.evolution_tool as tool
    importlib.reload(tool)
    return {"home": home, "skills": home / "skills", "tool": tool}


def _parse_tool_json(raw: str) -> dict:
    return json.loads(raw)


def _write_skill(skills_dir: Path, name: str, body: str = "body") -> Path:
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: t\nversion: 1.0\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return d


def test_evolution_tool_records_and_lists(evolution_tool_env):
    tool = evolution_tool_env["tool"]

    recorded = _parse_tool_json(tool.evolution_tool({
        "action": "record",
        "kind": "note",
        "title": "Manual note",
        "summary": "hello",
    }))
    listed = _parse_tool_json(tool.evolution_tool({"action": "list"}))

    assert recorded["success"] is True
    assert recorded["event"]["title"] == "Manual note"
    assert listed["success"] is True
    assert listed["events"][0]["title"] == "Manual note"


def test_evolution_tool_snapshot_and_rollback_by_event(evolution_tool_env):
    tool = evolution_tool_env["tool"]
    skills = evolution_tool_env["skills"]
    alpha = _write_skill(skills, "alpha", "old")

    snap = _parse_tool_json(tool.evolution_tool({"action": "snapshot", "reason": "before"}))
    assert snap["success"] is True
    event_id = snap["event"]["id"]

    import shutil
    shutil.rmtree(alpha)
    assert not alpha.exists()

    rolled = _parse_tool_json(tool.evolution_tool({"action": "rollback", "event_id": event_id}))
    assert rolled["success"] is True
    assert alpha.exists()


def test_evolution_tool_cycle_promotes_harness_rule(evolution_tool_env):
    tool = evolution_tool_env["tool"]
    from miho_cli import skill_curator

    skill_curator.record_skill_candidate(
        kind="failure_pattern",
        title="Repeated command retry",
        summary="The agent repeated a failing command instead of changing strategy.",
        evidence="trace",
        source="test",
    )

    result = _parse_tool_json(tool.evolution_tool({
        "action": "cycle",
        "min_hits": 1,
        "auto_promote": True,
    }))

    assert result["success"] is True
    assert result["promoted"]
    assert result["active_rules"]


def test_evolution_tool_autopilot_reaches_readiness(evolution_tool_env):
    tool = evolution_tool_env["tool"]

    result = _parse_tool_json(tool.evolution_tool({
        "action": "autopilot",
        "max_cycles": 3,
        "target_score": 100,
    }))

    assert result["success"] is True
    assert result["target_reached"] is True
    assert result["readiness"]["score"] == 100


def test_evolution_tool_doctor_reports_missing_before_training(evolution_tool_env):
    tool = evolution_tool_env["tool"]

    result = _parse_tool_json(tool.evolution_tool({"action": "doctor"}))

    assert result["success"] is True
    assert result["score"] < 100
    assert result["missing"]
