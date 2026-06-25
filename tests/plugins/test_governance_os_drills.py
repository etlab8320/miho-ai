"""Cross-domain drill coverage for Governance OS."""

from __future__ import annotations

from plugins.governance_os.drill import run_builtin_drills
from plugins.governance_os.registry import load_builtin_registry


def test_builtin_drills_cover_core_domains_and_promotion_safety() -> None:
    registry = load_builtin_registry()

    results = run_builtin_drills(registry)

    by_key = {result.key: result for result in results}
    assert {
        "hakjong_manual_pdf_block",
        "hakjong_missing_reviewer_fail",
        "hakjong_required_tool_review_required",
        "practical_reco_required_tool_review_required",
        "susi_manual_score_block",
        "susi_score_calculation_review_required",
        "life_record_ingest_review_required",
        "dev_destructive_git_block",
        "research_search_review_required",
        "discord_attachment_review_required",
        "memory_policy_review_required",
        "promotion_candidate_requires_rollback",
    }.issubset(by_key)
    assert all(result.passed for result in results)


def test_builtin_drill_suite_replays_policy_and_review_regressions() -> None:
    results = run_builtin_drills(load_builtin_registry())

    by_key = {result.key: result for result in results}
    assert by_key["hakjong_manual_pdf_block"].passed
    assert by_key["hakjong_missing_reviewer_fail"].passed
    assert by_key["hakjong_required_tool_review_required"].passed
    assert by_key["practical_reco_required_tool_review_required"].passed
    assert by_key["susi_manual_score_block"].passed
    assert by_key["susi_score_calculation_review_required"].passed
    assert by_key["life_record_ingest_review_required"].passed
    assert by_key["memory_policy_review_required"].passed
    assert all(result.passed for result in results)
