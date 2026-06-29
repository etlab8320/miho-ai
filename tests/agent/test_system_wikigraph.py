from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

from agent import system_wikigraph as wg


def _make_project(root: Path) -> None:
    (root / "gateway").mkdir()
    (root / "tests" / "e2e").mkdir(parents=True)
    (root / "tools").mkdir()
    (root / "gateway" / "platform.py").write_text("class Gateway:\n    pass\n", encoding="utf-8")
    (root / "tests" / "e2e" / "test_gateway_delivery.py").write_text("def test_gateway():\n    assert True\n", encoding="utf-8")
    (root / "tools" / "sample_tool.py").write_text("# registry.register('sample_tool')\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=root, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init"],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_init_wiki_creates_safe_scaffold(tmp_path, monkeypatch):
    home = tmp_path / "miho-home"
    monkeypatch.setenv("MIHO_HOME", str(home))

    result = wg.init_wiki()

    assert result["success"] is True
    assert (home / "system_wiki" / "SCHEMA.md").exists()
    assert (home / "system_wiki" / "policies" / "privacy-and-source-boundary.md").exists()
    assert (home / "system_graph" / "graph.db").exists()


def test_sync_project_indexes_files_tests_tools_and_events(tmp_path, monkeypatch):
    home = tmp_path / "miho-home"
    project = tmp_path / "project"
    project.mkdir()
    _make_project(project)
    monkeypatch.setenv("MIHO_HOME", str(home))
    evolution_dir = home / "evolution"
    evolution_dir.mkdir(parents=True)
    (evolution_dir / "events.jsonl").write_text(
        json.dumps({"id": 7, "kind": "note", "title": "seed", "changed_files": ["gateway/platform.py"]}) + "\n",
        encoding="utf-8",
    )

    result = wg.sync_project(project_root=project, full=True)

    assert result["success"] is True
    summary = result["summary"]
    assert summary["files"] >= 3
    assert summary["tests"] >= 1
    assert summary["events"] == 1
    assert (home / "system_wiki" / "raw" / "source-inventory.md").exists()

    conn = sqlite3.connect(home / "system_graph" / "graph.db")
    try:
        node_types = {row[0] for row in conn.execute("SELECT DISTINCT type FROM nodes")}
        assert "CodeFile" in node_types
        assert "Test" in node_types
        assert "EvolutionEvent" in node_types
        impact = wg.impact("gateway/platform.py")
        assert impact["nodes"]
    finally:
        conn.close()


def test_from_git_sync_prefers_changed_files(tmp_path, monkeypatch):
    home = tmp_path / "miho-home"
    project = tmp_path / "project"
    project.mkdir()
    _make_project(project)
    monkeypatch.setenv("MIHO_HOME", str(home))
    (project / "gateway" / "platform.py").write_text("class Gateway:\n    def changed(self):\n        return True\n", encoding="utf-8")

    result = wg.sync_project(project_root=project, from_git=True)

    assert "gateway/platform.py" in result["changed_files"]
    assert result["summary"]["files"] == 1


def test_graphrag_and_visualization_render_html(tmp_path, monkeypatch):
    home = tmp_path / "miho-home"
    project = tmp_path / "project"
    project.mkdir()
    _make_project(project)
    monkeypatch.setenv("MIHO_HOME", str(home))
    wg.sync_project(project_root=project, full=True)

    result = wg.graphrag("gateway", hops=2)
    assert result["nodes"]
    assert result["edges"]
    assert result["related_tests"]

    rendered = wg.render_graph_html("gateway", output_path=tmp_path / "map.html")
    out = Path(rendered["output_path"])
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "Miho System WikiGraph" in html
    assert "<svg" in html


def test_install_git_hooks_writes_nonblocking_hooks(tmp_path, monkeypatch):
    home = tmp_path / "miho-home"
    project = tmp_path / "project"
    project.mkdir()
    _make_project(project)
    monkeypatch.setenv("MIHO_HOME", str(home))

    result = wg.install_git_hooks(project_root=project)

    assert result["success"] is True
    assert len(result["installed"]) == len(wg.HOOK_NAMES)
    for hook in result["installed"]:
        text = Path(hook).read_text(encoding="utf-8")
        assert "MIHO_SYSTEM_WIKIGRAPH_HOOK" in text
        assert "evolution wikigraph sync --full" in text


def test_infer_tool_names_reads_multiline_registry_register(tmp_path):
    tool_file = tmp_path / "sample_tool.py"
    tool_file.write_text(
        "from tools.registry import registry\n"
        "registry.register(\n"
        "    name=\"sample_research_router\",\n"
        "    toolset=\"web\",\n"
        "    schema={},\n"
        "    handler=lambda args: '{}',\n"
        ")\n",
        encoding="utf-8",
    )

    assert "sample_research_router" in wg.infer_tool_names(tool_file)
