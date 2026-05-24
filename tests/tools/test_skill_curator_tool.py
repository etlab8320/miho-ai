"""Tests for skill curator candidate storage and tool dispatch."""

from __future__ import annotations

import json
import sqlite3

from miho_cli.skill_curator import (
    build_daily_skill_review_prompt,
    ensure_daily_skill_review_job,
    get_skill_curator_db_path,
    list_skill_candidates,
    record_skill_candidate,
    update_skill_candidate,
)
from tools.skill_curator_tool import SKILL_CURATOR_SCHEMA, skill_curator_tool


def test_record_candidate_persists_to_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    result = record_skill_candidate(
        kind="failure_pattern",
        title="Browser music request stalled",
        summary="Use computer_use for simple GUI playback instead of waiting on text tools.",
        evidence="Discord request waited several minutes before toolset was installed.",
        source="test",
    )

    assert result["success"] is True
    assert result["candidate"]["kind"] == "failure_pattern"
    with sqlite3.connect(get_skill_curator_db_path()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM skill_candidates").fetchone()[0]
    assert count == 1


def test_duplicate_candidate_increments_hits(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    kwargs = {
        "kind": "update_existing",
        "title": "KBO image quality gap",
        "summary": "Patch KBO skill to produce HTML-first report cards.",
        "target_skill": "kbo-game-analysis",
        "source": "test",
    }
    first = record_skill_candidate(evidence="No image attachment returned.", **kwargs)
    second = record_skill_candidate(evidence="Rendered card looked weaker than expected.", **kwargs)

    assert first["candidate"]["id"] == second["candidate"]["id"]
    assert second["candidate"]["hits"] == 2
    assert "weaker than expected" in second["candidate"]["evidence"]


def test_list_and_update_candidate_status(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    created = record_skill_candidate(
        kind="new_skill",
        title="Paca Peak browser login",
        summary="Create a workflow for login-aware browser automation.",
        evidence="User repeatedly asked for Discord-triggered Paca/Peak control.",
        suggested_skill="paca-peak-browser-automation",
    )

    pending = list_skill_candidates(status="pending")
    promoted = update_skill_candidate(
        created["candidate"]["id"],
        status="promoted",
        note="Created skill from candidate.",
    )

    assert pending[0]["title"] == "Paca Peak browser login"
    assert promoted["success"] is True
    assert promoted["candidate"]["status"] == "promoted"
    assert list_skill_candidates(status="pending") == []
    assert list_skill_candidates(status="promoted")[0]["id"] == created["candidate"]["id"]


def test_tool_dispatch_records_lists_and_dismisses(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    record = json.loads(
        skill_curator_tool(
            {
                "action": "record_candidate",
                "kind": "failure_pattern",
                "title": "Progress bar mismatch",
                "summary": "Avoid fake progress percentages in Discord cards.",
                "evidence": "Past progress cards did not match actual work.",
            }
        )
    )
    listed = json.loads(skill_curator_tool({"action": "list_candidates"}))
    dismissed = json.loads(
        skill_curator_tool(
            {
                "action": "dismiss_candidate",
                "candidate_id": record["candidate"]["id"],
                "note": "Kept as UX idea for later.",
            }
        )
    )

    assert record["success"] is True
    assert listed["candidates"][0]["title"] == "Progress bar mismatch"
    assert dismissed["candidate"]["status"] == "dismissed"


def test_schema_guides_failure_and_skill_update_use():
    description = SKILL_CURATOR_SCHEMA["description"]

    assert "failed attempts" in description
    assert "update_existing" in description
    assert "new official workflow skill" in description


def test_daily_skill_review_job_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    first = ensure_daily_skill_review_job()
    second = ensure_daily_skill_review_job()

    assert first["success"] is True
    assert first["created"] is True
    assert second["created"] is False
    assert second["job"]["name"] == "skill-curator-daily-review"
    assert "skill_curator(action='list_candidates'" in build_daily_skill_review_prompt()
