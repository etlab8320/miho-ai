from __future__ import annotations

import sqlite3
from pathlib import Path

from agent import system_wikigraph as wg
from agent import system_wikigraph_relationships as rel


def _make_project(root: Path) -> None:
    (root / "tools").mkdir(parents=True)
    (root / "skills" / "productivity" / "reviewer-guard").mkdir(parents=True)
    (root / "tools" / "sample_tool.py").write_text(
        "from tools.registry import registry\n"
        "registry.register(\n"
        "    name='sample_research_router',\n"
        "    toolset='research',\n"
        "    schema={},\n"
        "    handler=lambda args: '{}',\n"
        ")\n",
        encoding="utf-8",
    )
    (root / "skills" / "productivity" / "reviewer-guard" / "SKILL.md").write_text(
        "---\n"
        "name: reviewer-guard\n"
        "description: Use sample_research_router before reporting reviewed results.\n"
        "---\n"
        "# Reviewer Guard\n\n"
        "Use `sample_research_router` to prevent `reviewer_missing` failure.\n"
        "This skill mitigates timeout and evidence missing cases.\n",
        encoding="utf-8",
    )


def test_relationship_sync_links_skill_tool_and_failure(tmp_path, monkeypatch) -> None:
    home = tmp_path / "miho-home"
    project = tmp_path / "project"
    project.mkdir()
    _make_project(project)
    monkeypatch.setenv("MIHO_HOME", str(home))

    wg.sync_project(project_root=project, full=True)
    result = rel.sync_relationships(project_root=project)

    assert result["success"] is True
    assert result["summary"]["skill_tool_edges"] >= 1
    assert result["summary"]["mitigation_edges"] >= 1

    conn = sqlite3.connect(home / "system_graph" / "graph.db")
    try:
        uses = conn.execute(
            "SELECT 1 FROM edges WHERE relation='uses' AND target_id='tool:sample_research_router'"
        ).fetchone()
        mitigates = conn.execute(
            "SELECT 1 FROM edges WHERE relation='mitigates' AND target_id LIKE 'failure:%reviewer_missing%'"
        ).fetchone()
    finally:
        conn.close()
    assert uses is not None
    assert mitigates is not None


def test_relationship_sync_links_governance_agents_tools_and_failures(tmp_path, monkeypatch) -> None:
    home = tmp_path / "miho-home"
    monkeypatch.setenv("MIHO_HOME", str(home))

    result = rel.sync_relationships()

    assert result["summary"]["governance_edges"] >= 1
    conn = sqlite3.connect(home / "system_graph" / "graph.db")
    try:
        agent = conn.execute("SELECT 1 FROM nodes WHERE type='Agent' LIMIT 1").fetchone()
        tool_prevents = conn.execute(
            "SELECT 1 FROM edges WHERE relation='prevents' AND source_id LIKE 'tool:%' LIMIT 1"
        ).fetchone()
        agent_uses_tool = conn.execute(
            "SELECT 1 FROM edges WHERE relation='uses_tool' AND source_id LIKE 'agent:%' LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert agent is not None
    assert tool_prevents is not None
    assert agent_uses_tool is not None


def test_governance_relationship_html_renders_map(tmp_path, monkeypatch) -> None:
    home = tmp_path / "miho-home"
    monkeypatch.setenv("MIHO_HOME", str(home))
    rel.sync_relationships()
    output = tmp_path / "governance-map.html"

    rendered = rel.render_governance_relationship_html(output_path=output)

    assert rendered["success"] is True
    html = output.read_text(encoding="utf-8")
    assert "Miho Governance Relationship Map" in html
    assert "uses_tool" in html
    assert "prevents" in html
