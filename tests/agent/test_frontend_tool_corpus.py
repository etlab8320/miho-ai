from __future__ import annotations

import json
import sqlite3

from agent import frontend_tool_corpus as corpus


def test_frontend_tool_corpus_syncs_metadata_and_wiki_pages(tmp_path, monkeypatch) -> None:
    home = tmp_path / "miho-home"
    monkeypatch.setenv("MIHO_HOME", str(home))

    result = corpus.sync_frontend_tool_corpus()

    assert result["success"] is True
    assert result["summary"]["tools_indexed"] >= 10
    assert result["summary"]["stacks_indexed"] == 3
    assert result["categories"]["korea_ux_runtime"] >= 3

    recommended = home / "system_wiki" / "frontend-tools" / "recommended-frontend-tools.md"
    stack = home / "system_wiki" / "frontend-tools" / "max-frontend-stack.md"
    drills = home / "system_wiki" / "frontend-tools" / "ui-self-harness-candidates.md"
    policy = home / "system_wiki" / "policies" / "frontend-tool-adoption-boundary.md"

    recommended_text = recommended.read_text(encoding="utf-8")
    assert "shadcn-ui/ui" in recommended_text
    assert "Toss Suspensive" in recommended_text
    assert "no package is installed" in recommended_text
    assert "runtime dependency" not in recommended_text.lower() or "StyleSeed" in recommended_text
    assert "max_frontend_standard" in stack.read_text(encoding="utf-8")
    assert "frontend_ui_drill:tool_adoption_requires_project_target" in drills.read_text(encoding="utf-8")
    assert "target project" in policy.read_text(encoding="utf-8")

    conn = sqlite3.connect(home / "system_graph" / "graph.db")
    try:
        tool_count = conn.execute("SELECT count(*) FROM nodes WHERE type='FrontendTool'").fetchone()[0]
        stack_edge = conn.execute(
            "SELECT 1 FROM edges WHERE relation='recommends_tool' AND source_id='frontend-stack:max_frontend_standard'"
        ).fetchone()
        row = conn.execute(
            "SELECT metadata_json FROM nodes WHERE id='frontend-tool:shadcn-ui-ui'"
        ).fetchone()
    finally:
        conn.close()
    assert tool_count >= 10
    assert stack_edge is not None
    assert row is not None
    metadata = json.loads(row[0])
    assert metadata["license"] == "MIT"
    assert metadata["adoption"] == "standard_candidate"


def test_frontend_tool_corpus_candidates_are_not_active_runtime_rules() -> None:
    candidates = corpus.build_ui_self_harness_candidates()

    assert candidates
    assert all(item["activation_policy"] == "candidate_only_until_test_implemented" for item in candidates)
    assert any("project_target" in item["id"] for item in candidates)