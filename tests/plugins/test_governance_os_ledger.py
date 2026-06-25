"""Outcome ledger query tests for Governance OS."""

from __future__ import annotations

import importlib

from plugins.governance_os.ledger import OutcomeLedgerEntry, list_outcomes, record_outcome


def _reload_evolution_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants
    from agent import evolution

    importlib.reload(miho_constants)
    importlib.reload(evolution)
    return evolution


def test_outcome_ledger_records_governance_note_event(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    entry = OutcomeLedgerEntry(
        request_id="req-1",
        playbook_key="academy_hakjong_report",
        agent_chain=("dispatcher", "result_reviewer"),
        tools_used=("academy_hakjong_report_package",),
        review_status="pass",
        artifact_paths=("/tmp/report.pdf",),
    )

    event = record_outcome(entry)

    assert event["kind"] == "note"
    assert event["title"] == "Governance outcome academy_hakjong_report"
    outcome = event["metadata"]["governance_outcome"]
    assert outcome["request_id"] == "req-1"
    assert outcome["review_status"] == "pass"
    assert evolution.list_events(limit=1)[0]["id"] == event["id"]


def test_list_outcomes_returns_recent_governance_outcomes(tmp_path, monkeypatch) -> None:
    _reload_evolution_home(tmp_path, monkeypatch)
    record_outcome(
        OutcomeLedgerEntry(
            request_id="req-academy-pass",
            playbook_key="academy_hakjong_report",
            tools_used=("academy_hakjong_report_package",),
            review_status="pass",
        )
    )
    record_outcome(
        OutcomeLedgerEntry(
            request_id="req-discord-fail",
            playbook_key="discord_attachment_delivery",
            tools_used=("media_delivery_contract",),
            review_status="fail",
            failures=("reviewer_missing",),
        )
    )

    outcomes = list_outcomes(limit=10)

    assert [item["request_id"] for item in outcomes] == [
        "req-discord-fail",
        "req-academy-pass",
    ]
    assert outcomes[0]["event_id"] > outcomes[1]["event_id"]
    assert outcomes[0]["event_status"] == "failed"


def test_list_outcomes_filters_by_playbook(tmp_path, monkeypatch) -> None:
    _reload_evolution_home(tmp_path, monkeypatch)
    record_outcome(
        OutcomeLedgerEntry(
            request_id="req-academy-pass",
            playbook_key="academy_hakjong_report",
            review_status="pass",
        )
    )
    record_outcome(
        OutcomeLedgerEntry(
            request_id="req-discord-pass",
            playbook_key="discord_attachment_delivery",
            review_status="pass",
        )
    )

    outcomes = list_outcomes(
        limit=10,
        playbook_key="discord_attachment_delivery",
    )

    assert len(outcomes) == 1
    assert outcomes[0]["request_id"] == "req-discord-pass"
    assert outcomes[0]["playbook_key"] == "discord_attachment_delivery"
