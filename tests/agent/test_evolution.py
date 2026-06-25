"""Tests for Miho Evolution OS ledger and rollback glue."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def evolution_env(monkeypatch, tmp_path):
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
    return {"home": home, "skills": home / "skills", "evolution": evolution, "backup": curator_backup}


def _write_skill(skills_dir: Path, name: str, body: str = "body") -> Path:
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: t\nversion: 1.0\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return d


def test_record_event_appends_jsonl(evolution_env):
    ev = evolution_env["evolution"]

    event = ev.record_event(
        kind="failure_pattern",
        title="Repeated render timeout",
        summary="Chrome render timed out twice",
    )

    assert event["id"] == 1
    assert event["kind"] == "failure_pattern"
    assert ev.events_path().exists()
    rows = ev.list_events(limit=None)
    assert len(rows) == 1
    assert rows[0]["title"] == "Repeated render timeout"


def test_snapshot_skills_records_event_with_snapshot_id(evolution_env):
    ev = evolution_env["evolution"]
    _write_skill(evolution_env["skills"], "alpha")

    result = ev.snapshot_skills(reason="unit-test")

    assert result["success"] is True
    assert result["snapshot_id"]
    assert result["event"]["kind"] == "snapshot"
    assert result["event"]["snapshot_id"] == result["snapshot_id"]


def test_rollback_event_uses_attached_snapshot(evolution_env):
    ev = evolution_env["evolution"]
    skills = evolution_env["skills"]
    alpha = _write_skill(skills, "alpha", "old")
    snap_result = ev.snapshot_skills(reason="before-delete")
    snapshot_event_id = snap_result["event"]["id"]

    import shutil
    shutil.rmtree(alpha)
    assert not alpha.exists()

    ok, msg, data = ev.rollback_event(snapshot_event_id)

    assert ok, msg
    assert alpha.exists()
    assert "old" in (alpha / "SKILL.md").read_text(encoding="utf-8")
    assert data["rollback_event"]["kind"] == "rollback"
    assert data["rollback_event"]["proposal_id"] == snapshot_event_id


def test_skill_manage_records_evolution_and_snapshot(monkeypatch, evolution_env):
    # Reload skill manager after MIHO_HOME is isolated so module constants point
    # at the test skill tree.
    import tools.skill_manager_tool as sm
    importlib.reload(sm)

    content = "---\nname: alpha\ndescription: test skill\nversion: 1.0\n---\n\nBody\n"
    result = json.loads(sm.skill_manage(action="create", name="alpha", content=content))

    assert result["success"] is True
    assert result["evolution"]["event_id"] >= 1
    assert result["evolution"]["snapshot_id"] is not None

    ev = evolution_env["evolution"]
    event = ev.get_event(result["evolution"]["event_id"])
    assert event is not None
    assert event["kind"] == "promotion"
    assert event["metadata"]["action"] == "create"
    assert event["snapshot_id"] == result["evolution"]["snapshot_id"]


def test_mine_skill_candidates_imports_pending_curator_items(evolution_env):
    ev = evolution_env["evolution"]
    from miho_cli import skill_curator

    skill_curator.record_skill_candidate(
        kind="failure_pattern",
        title="Repeated command retry",
        summary="The agent retried the same failing shell command.",
        evidence="test evidence",
        source="test",
    )

    first = ev.mine_skill_candidates(limit=10)
    second = ev.mine_skill_candidates(limit=10)

    assert first["success"] is True
    assert len(first["created"]) == 1
    assert first["created"][0]["kind"] == "failure_pattern"
    assert len(second["created"]) == 0
    assert len(second["skipped"]) == 1


def test_generate_proposals_clusters_failure_patterns(evolution_env):
    ev = evolution_env["evolution"]
    ev.record_event(
        kind="failure_pattern",
        title="Repeated command retry",
        summary="The agent retried the same failing shell command twice.",
        evidence="pytest failed, then the identical command was run again.",
    )
    ev.record_event(
        kind="failure_pattern",
        title="Repeated command retry",
        summary="The same command retry pattern happened again.",
        evidence="npm build failed twice with no new evidence.",
    )

    result = ev.generate_proposals(min_hits=2)

    assert result["success"] is True
    assert len(result["created"]) == 1
    proposal = result["created"][0]
    assert proposal["kind"] == "proposal"
    assert proposal["status"] == "proposed"
    assert proposal["metadata"]["source_event_ids"] == [1, 2]
    assert "Repeated command retry" in proposal["title"]


def test_validate_and_promote_proposal_creates_active_harness_rule(evolution_env):
    ev = evolution_env["evolution"]
    proposal = ev.record_event(
        kind="proposal",
        title="Harness rule: stop repeated command retry",
        summary="If the same command fails twice, stop and inspect the failure before retrying.",
        evidence="Two failure events showed identical command retries.",
        status="proposed",
        metadata={"source_event_ids": [1, 2]},
    )

    validation = ev.validate_proposal(proposal["id"])
    promotion = ev.promote_proposal(proposal["id"])
    rules = ev.list_harness_rules()

    assert validation["success"] is True
    assert validation["event"]["status"] == "validated"
    assert promotion["success"] is True
    assert promotion["event"]["kind"] == "harness_rule"
    assert promotion["event"]["status"] == "active"
    assert rules[0]["proposal_id"] == proposal["id"]
    assert "same command fails twice" in rules[0]["summary"]


def test_run_evolution_cycle_mines_proposes_validates_and_promotes(evolution_env):
    ev = evolution_env["evolution"]
    from miho_cli import skill_curator

    for evidence in ["first retry trace", "second retry trace"]:
        skill_curator.record_skill_candidate(
            kind="failure_pattern",
            title="Repeated command retry",
            summary="The agent repeated a failing command instead of changing strategy.",
            evidence=evidence,
            source="test",
        )

    result = ev.run_evolution_cycle(min_hits=1, auto_promote=True)

    assert result["success"] is True
    assert result["mined"]["created"]
    assert result["proposals"]["created"]
    assert result["promoted"]
    assert ev.list_harness_rules()


def test_promote_proposal_is_idempotent_without_extra_validation_events(evolution_env):
    ev = evolution_env["evolution"]
    proposal = ev.record_event(
        kind="proposal",
        title="Harness rule: inspect before retry",
        summary="If the same command fails twice, inspect before retrying.",
        evidence="failure traces",
        status="proposed",
    )

    first = ev.promote_proposal(proposal["id"])
    second = ev.promote_proposal(proposal["id"])
    proposal_events = ev.list_events(limit=None, kind="proposal")
    harness_rules = ev.list_harness_rules()

    assert first["success"] is True
    assert second["success"] is True
    assert second["already_active"] is True
    assert len(harness_rules) == 1
    assert len([e for e in proposal_events if e.get("status") == "validated"]) == 1


def test_rollback_harness_rule_event_deactivates_rule(evolution_env):
    ev = evolution_env["evolution"]
    proposal = ev.record_event(
        kind="proposal",
        title="Harness rule: inspect before retry",
        summary="If the same command fails twice, inspect before retrying.",
        evidence="failure traces",
        status="proposed",
    )
    promotion = ev.promote_proposal(proposal["id"])

    ok, msg, data = ev.rollback_event(promotion["event"]["id"])
    rules = ev.list_harness_rules()

    assert ok is True
    assert "deactivated" in msg
    assert data["rollback_event"]["kind"] == "rollback"
    assert rules[0]["status"] == "rolled_back"


def test_training_ground_creates_promoted_rules_and_records_run(evolution_env):
    ev = evolution_env["evolution"]

    result = ev.run_training_ground(auto_promote=True)

    assert result["success"] is True
    assert result["training_failures"] >= 2
    assert result["promoted"]
    assert ev.list_harness_rules()
    notes = [e for e in ev.list_events(limit=None, kind="note") if e["title"] == "Evolution training ground run"]
    assert notes
    assert notes[0]["metadata"]["training_ground"] is True


def test_immunity_check_rejects_unsafe_and_rolls_back_drill_rule(evolution_env):
    ev = evolution_env["evolution"]

    result = ev.run_immunity_check()

    assert result["success"] is True
    assert result["passed"] is True
    assert result["checks"]["unsafe_proposal_rejected"]["passed"] is True
    assert result["checks"]["rollback_drill"]["passed"] is True
    rolled = [r for r in ev.list_harness_rules() if r.get("status") == "rolled_back"]
    assert rolled


def test_readiness_report_reaches_100_after_loop(evolution_env):
    ev = evolution_env["evolution"]

    result = ev.run_evolution_autopilot(max_cycles=3, target_score=100)
    report = ev.evolution_readiness_report()

    assert result["success"] is True
    assert result["target_reached"] is True
    assert report["score"] == 100
    assert report["level"] == "operational-organism"
    assert not report["missing"]
