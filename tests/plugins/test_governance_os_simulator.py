"""Scenario simulator coverage for Governance OS."""

from __future__ import annotations

from plugins.governance_os.registry import load_builtin_registry
from plugins.governance_os.simulator import run_simulation_suite


def test_simulation_suite_covers_core_governance_paths() -> None:
    results = run_simulation_suite(load_builtin_registry())

    by_key = {result.key: result for result in results}
    assert {
        "discord_attachment_success",
        "discord_attachment_missing_reviewer_retry",
        "academy_manual_pdf_block",
        "practical_reco_missing_reviewer_retry",
        "susi_manual_score_block",
        "susi_score_calculation_missing_reviewer_retry",
        "life_record_needs_human_review_hold",
        "dev_deploy_requires_approval",
        "research_source_review_success",
        "memory_privacy_missing_retry",
    }.issubset(by_key)
    assert all(result.passed for result in results)


def test_simulation_success_case_reaches_delivery_state() -> None:
    results = {result.key: result for result in run_simulation_suite(load_builtin_registry())}

    result = results["discord_attachment_success"]

    assert result.playbook_key == "discord_attachment_delivery"
    assert result.policy_action == "review_required"
    assert result.review_status == "pass"
    assert result.final_status == "deliver"
