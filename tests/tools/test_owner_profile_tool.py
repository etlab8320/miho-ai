"""Tests for Miho owner profile storage and tool dispatch."""

from __future__ import annotations

import json
import sqlite3

from miho_cli.owner_profile import (
    append_profile_event,
    append_to_master_profile,
    build_daily_summary_prompt,
    ensure_daily_summary_job,
    get_master_profile_path,
    get_timeline_db_path,
    list_profile_events,
    read_master_profile,
    replace_master_profile,
)
from tools.owner_profile_tool import OWNER_PROFILE_SCHEMA, owner_profile_tool


def test_replace_master_profile_persists_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    result = replace_master_profile("# Max\n\nMiho context.", source="test")

    assert result["success"] is True
    assert get_master_profile_path().read_text(encoding="utf-8") == "# Max\n\nMiho context.\n"
    assert "Miho context" in read_master_profile()


def test_append_profile_event_persists_to_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    result = append_profile_event(
        category="business",
        title="Paca direction",
        content="Max wants academy operations automation.",
        source="test",
    )

    assert result["success"] is True
    events = list_profile_events()
    assert events[0]["title"] == "Paca direction"
    assert events[0]["category"] == "business"
    with sqlite3.connect(get_timeline_db_path()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM profile_events").fetchone()[0]
    assert count == 1


def test_append_to_master_writes_markdown_and_timeline(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    result = append_to_master_profile(
        title="Health context",
        content="Max is tracking body condition.",
        source="test",
    )

    assert result["success"] is True
    content = get_master_profile_path().read_text(encoding="utf-8")
    assert "## Health context" in content
    assert "Max is tracking body condition." in content
    assert list_profile_events(category="master_profile")[0]["title"] == "Health context"


def test_tool_reads_and_lists_events(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    replace_master_profile("# Owner Master Profile\n", source="test")
    append_profile_event("identity", "Role", "Director and product owner.", source="test")

    read_result = json.loads(owner_profile_tool({"action": "read_master"}))
    list_result = json.loads(owner_profile_tool({"action": "list_events", "limit": 1}))

    assert read_result["success"] is True
    assert "Owner Master Profile" in read_result["content"]
    assert list_result["events"][0]["title"] == "Role"


def test_schema_guides_autobiography_use():
    description = OWNER_PROFILE_SCHEMA["description"]

    assert "autobiography-like timeline" in description
    assert "USER.md" in description
    assert "deep context" in description


def test_daily_summary_job_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    first = ensure_daily_summary_job()
    second = ensure_daily_summary_job()

    assert first["success"] is True
    assert first["created"] is True
    assert second["created"] is False
    assert second["job"]["name"] == "owner-profile-daily-summary"
    assert "오늘 한 작업" in build_daily_summary_prompt()
