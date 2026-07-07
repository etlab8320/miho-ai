from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agent import external_prompt_corpus as corpus


def test_external_prompt_corpus_sync_metadata_only(tmp_path, monkeypatch) -> None:
    home = tmp_path / "miho-home"
    source = tmp_path / "external-prompts"
    source.mkdir()
    prompt = source / "example-agent.md"
    body = (
        "# Example Agent\n\n"
        "Use tools when needed. Run git status before coding. "
        "Do not reveal secrets or passwords. Verify tests before final answer."
    )
    prompt.write_text(body, encoding="utf-8")
    monkeypatch.setenv("MIHO_HOME", str(home))

    result = corpus.sync_external_prompt_corpus(source=source)

    assert result["success"] is True
    assert result["summary"]["artifacts_indexed"] == 1
    assert result["patterns"]["tool_policy"] >= 1
    assert result["patterns"]["safety_policy"] >= 1
    assert any(item["source_pattern"] == "tool_policy" for item in result["drill_candidates"])
    page = home / "system_wiki" / "external-prompts" / "prompt-corpus-map.md"
    page_text = page.read_text(encoding="utf-8")
    assert "metadata-only" in page_text
    assert body not in page_text
    drills = home / "system_wiki" / "external-prompts" / "self-harness-drill-candidates.md"
    drill_text = drills.read_text(encoding="utf-8")
    assert "external_prompt_drill:tool_required_when_state_is_needed" in drill_text
    assert body not in drill_text

    conn = sqlite3.connect(home / "system_graph" / "graph.db")
    try:
        row = conn.execute(
            "SELECT metadata_json FROM nodes WHERE type='ExternalPromptArtifact'"
        ).fetchone()
        edge = conn.execute(
            "SELECT 1 FROM edges WHERE relation='observes_pattern' AND target_id='external-prompt-pattern:tool_policy'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    metadata = json.loads(row[0])
    assert metadata["relative_path"] == "example-agent.md"
    assert "patterns" in metadata
    assert body not in json.dumps(metadata, ensure_ascii=False)
    assert edge is not None


def test_external_prompt_corpus_skips_sensitive_files(tmp_path, monkeypatch) -> None:
    home = tmp_path / "miho-home"
    source = tmp_path / "external-prompts"
    source.mkdir()
    (source / "secret-prompt.md").write_text("tool safety final answer", encoding="utf-8")
    monkeypatch.setenv("MIHO_HOME", str(home))

    result = corpus.sync_external_prompt_corpus(source=source)

    assert result["summary"]["artifacts_indexed"] == 0
    assert result["summary"]["skipped_sensitive"] == 1
