"""Promotion activation tests for Governance OS registry rules."""

from __future__ import annotations

import importlib

import pytest

from plugins.governance_os.promotion import (
    PromotionCandidate,
    activate_promotion_candidate,
    find_promotion_candidates,
    record_promotion_candidate,
    validate_candidate,
)
from plugins.governance_os.registry import load_builtin_registry, registry_from_mapping


def _reload_evolution_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants
    from agent import evolution

    importlib.reload(miho_constants)
    importlib.reload(evolution)
    return evolution


def _test_receipt(name: str) -> dict[str, object]:
    return {
        "name": name,
        "status": "passed",
        "exit_code": 0,
        "command": f"pytest {name}",
        "evidence": f"{name} passed",
    }


def test_promotion_activation_requires_passed_tests(tmp_path, monkeypatch) -> None:
    _reload_evolution_home(tmp_path, monkeypatch)
    candidate = PromotionCandidate(
        playbook_key="academy_hakjong_report",
        source_failure="manual PDF bypass repeated",
        recurrence_count=2,
        proposed_policy="block write_file for 학종 reports",
        evidence=("failure-1", "failure-2"),
        tests_required=("test_guard_blocks_manual_pdf",),
        rollback="rollback active registry snapshot",
    )

    with pytest.raises(ValueError, match="test_receipts is required"):
        activate_promotion_candidate(
            candidate,
            action="add_forbidden_tool",
            value="write_file",
            tests_passed=(),
            reason="no tests should not promote",
        )


def test_promotion_activation_rejects_string_only_test_claims(tmp_path, monkeypatch) -> None:
    _reload_evolution_home(tmp_path, monkeypatch)
    candidate = PromotionCandidate(
        playbook_key="academy_hakjong_report",
        source_failure="manual PDF bypass repeated",
        recurrence_count=2,
        proposed_policy="block write_file for 학종 reports",
        evidence=("failure-1", "failure-2"),
        tests_required=("test_guard_blocks_manual_pdf",),
        rollback="rollback active registry snapshot",
    )

    with pytest.raises(ValueError, match="invalid test receipts"):
        activate_promotion_candidate(
            candidate,
            action="add_forbidden_tool",
            value="write_file",
            tests_passed=("test_guard_blocks_manual_pdf",),
            test_receipts=("test_guard_blocks_manual_pdf",),
            reason="string claims should not promote",
        )


def test_promotion_activation_rejects_legacy_passed_tests_without_receipts(
    tmp_path,
    monkeypatch,
) -> None:
    _reload_evolution_home(tmp_path, monkeypatch)
    candidate = PromotionCandidate(
        playbook_key="academy_hakjong_report",
        source_failure="manual PDF bypass repeated",
        recurrence_count=2,
        proposed_policy="block write_file for 학종 reports",
        evidence=("failure-1", "failure-2"),
        tests_required=("test_guard_blocks_manual_pdf",),
        rollback="rollback active registry snapshot",
    )

    with pytest.raises(ValueError, match="test_receipts is required"):
        activate_promotion_candidate(
            candidate,
            action="add_forbidden_tool",
            value="write_file",
            tests_passed=("test_guard_blocks_manual_pdf",),
            reason="legacy strings should not promote",
        )


def test_promotion_activation_rejects_failed_receipts(tmp_path, monkeypatch) -> None:
    _reload_evolution_home(tmp_path, monkeypatch)
    candidate = PromotionCandidate(
        playbook_key="academy_hakjong_report",
        source_failure="manual PDF bypass repeated",
        recurrence_count=2,
        proposed_policy="block write_file for 학종 reports",
        evidence=("failure-1", "failure-2"),
        tests_required=("test_guard_blocks_manual_pdf",),
        rollback="rollback active registry snapshot",
    )
    receipt = _test_receipt("test_guard_blocks_manual_pdf")
    receipt["status"] = "failed"
    receipt["exit_code"] = 0

    with pytest.raises(ValueError, match="required tests did not pass"):
        activate_promotion_candidate(
            candidate,
            action="add_forbidden_tool",
            value="write_file",
            test_receipts=(receipt,),
            reason="failed receipt should not promote",
        )


def test_promotion_activation_rejects_misleading_receipt_names(tmp_path, monkeypatch) -> None:
    _reload_evolution_home(tmp_path, monkeypatch)
    candidate = PromotionCandidate(
        playbook_key="academy_hakjong_report",
        source_failure="manual PDF bypass repeated",
        recurrence_count=2,
        proposed_policy="block write_file for 학종 reports",
        evidence=("failure-1", "failure-2"),
        tests_required=("tests/plugins/test_governance_os_policy.py",),
        rollback="rollback active registry snapshot",
    )
    receipt = _test_receipt("fake tests/plugins/test_governance_os_policy.py claim")

    with pytest.raises(ValueError, match="required tests did not pass"):
        activate_promotion_candidate(
            candidate,
            action="add_forbidden_tool",
            value="write_file",
            test_receipts=(receipt,),
            reason="misleading receipt name should not promote",
        )


def test_promotion_candidates_detect_repeated_outcome_failures(tmp_path, monkeypatch) -> None:
    _reload_evolution_home(tmp_path, monkeypatch)

    from plugins.governance_os.ledger import OutcomeLedgerEntry, record_outcome

    for index in range(2):
        record_outcome(
            OutcomeLedgerEntry(
                request_id=f"req-discord-reviewer-missing-{index}",
                playbook_key="discord_attachment_delivery",
                tools_used=("media_delivery_contract",),
                review_status="fail",
                failures=("reviewer_missing",),
                created_at=f"2026-06-25T00:00:0{index}+00:00",
            )
        )

    candidates = find_promotion_candidates(limit=10, min_recurrence=2)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.playbook_key == "discord_attachment_delivery"
    assert candidate.source_failure == "reviewer_missing"
    assert candidate.recurrence_count == 2
    assert "review gate" in candidate.proposed_policy
    assert "tests/e2e/test_discord_governance_delivery.py" in candidate.tests_required
    assert candidate.rollback == "rollback active governance registry snapshot"
    assert all("req-discord-reviewer-missing" in item for item in candidate.evidence)


def test_promotion_candidate_requires_focused_policy_tests_after_split(
    tmp_path,
    monkeypatch,
) -> None:
    _reload_evolution_home(tmp_path, monkeypatch)

    from plugins.governance_os.ledger import OutcomeLedgerEntry, record_outcome

    for index in range(2):
        record_outcome(
            OutcomeLedgerEntry(
                request_id=f"req-academy-forbidden-tool-{index}",
                playbook_key="academy_hakjong_report",
                tools_used=("write_file",),
                review_status="fail",
                failures=("forbidden_tool",),
            )
        )

    [candidate] = find_promotion_candidates(limit=10, min_recurrence=2)

    assert candidate.playbook_key == "academy_hakjong_report"
    assert candidate.source_failure == "forbidden_tool"
    assert "tests/plugins/test_governance_os_policy.py" in candidate.tests_required
    assert "tests/plugins/test_governance_os_drills.py" in candidate.tests_required
    assert "tests/plugins/test_governance_os_promotion_activation.py" in candidate.tests_required
    assert "tests/plugins/test_governance_os_foundation.py" not in candidate.tests_required


def test_promotion_candidate_records_failure_pattern_with_safety_metadata(tmp_path, monkeypatch) -> None:
    _reload_evolution_home(tmp_path, monkeypatch)

    candidate = PromotionCandidate(
        playbook_key="academy_hakjong_report",
        source_failure="학종 PDF를 도구 없이 직접 만들려고 했다.",
        recurrence_count=2,
        proposed_policy="academy_hakjong_report는 academy_hakjong_report_package만 허용한다.",
        evidence=("blocked write_file attempt", "user stopped manual PDF"),
        tests_required=("test_governance_pre_tool_guard_blocks_playbook_forbidden_tool",),
        rollback="remove or disable the promoted playbook rule",
    )

    event = record_promotion_candidate(candidate)

    assert event["kind"] == "failure_pattern"
    assert event["status"] == "candidate"
    metadata = event["metadata"]["governance_promotion_candidate"]
    assert metadata["recurrence_count"] == 2
    assert metadata["rollback"] == "remove or disable the promoted playbook rule"


def test_promotion_candidate_rejects_unsafe_one_off_candidate() -> None:
    candidate = PromotionCandidate(
        playbook_key="academy_hakjong_report",
        source_failure="one off",
        recurrence_count=1,
        proposed_policy="change routing",
        evidence=("single event",),
        tests_required=("test_name",),
        rollback="revert rule",
    )

    errors = validate_candidate(candidate)

    assert "recurrence_count must be at least 2" in errors


def test_promotion_activation_adds_rule_and_keeps_rollback_snapshot(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    from plugins.governance_os.versioning import load_runtime_registry, rollback_registry_snapshot

    base = load_builtin_registry()
    relaxed_payload = base.to_payload()
    relaxed_payload["playbooks"]["academy_hakjong_report"]["forbidden_tools"].remove("write_file")
    relaxed = registry_from_mapping(relaxed_payload)
    candidate = PromotionCandidate(
        playbook_key="academy_hakjong_report",
        source_failure="manual PDF bypass repeated",
        recurrence_count=2,
        proposed_policy="block write_file for 학종 reports",
        evidence=("blocked terminal attempt", "blocked write_file attempt"),
        tests_required=("test_governance_pre_tool_guard_blocks_playbook_forbidden_tool",),
        rollback="rollback active registry snapshot",
    )

    activation = activate_promotion_candidate(
        candidate,
        registry=relaxed,
        action="add_forbidden_tool",
        value="write_file",
        test_receipts=(
            _test_receipt("test_governance_pre_tool_guard_blocks_playbook_forbidden_tool"),
        ),
        reason="promote repeated manual PDF block",
        created_at="2026-06-25T00:00:03+00:00",
    )
    runtime = load_runtime_registry()

    assert "write_file" in runtime.get_playbook("academy_hakjong_report").forbidden_tools
    assert activation.rollback_snapshot_id
    latest = evolution.list_events(limit=1)[0]
    metadata = latest["metadata"]["governance_promotion_activation"]
    assert metadata["snapshot_id"] == activation.snapshot_id
    assert metadata["rollback_snapshot_id"] == activation.rollback_snapshot_id
    assert metadata["test_receipts"][0]["name"] == (
        "test_governance_pre_tool_guard_blocks_playbook_forbidden_tool"
    )

    rollback_registry_snapshot(activation.rollback_snapshot_id, reason="test rollback")
    rolled_back = load_runtime_registry()
    rollback_event = evolution.list_events(limit=1)[0]
    rollback_link = rollback_event["metadata"]["governance_promotion_rollback"]

    assert "write_file" not in rolled_back.get_playbook("academy_hakjong_report").forbidden_tools
    assert rollback_event["kind"] == "rollback"
    assert rollback_link["target_promotion_event_id"] == activation.event_id
    assert rollback_link["promoted_snapshot_id"] == activation.snapshot_id
    assert rollback_link["rollback_snapshot_id"] == activation.rollback_snapshot_id
    assert rollback_link["candidate"]["playbook_key"] == "academy_hakjong_report"
