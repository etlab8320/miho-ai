"""Long-horizon Self-Harness quality report tests."""

from __future__ import annotations

from plugins.governance_os.self_harness_quality import build_self_harness_quality_report


def test_self_harness_quality_passes_without_recorded_failures() -> None:
    report = build_self_harness_quality_report(outcomes=[])

    assert report.ready
    assert report.score == 100
    assert report.status == "no_failures_observed"
    assert report.to_payload()["recurrent_failures"] == []


def test_self_harness_quality_flags_recurrent_timeout_failures() -> None:
    outcomes = [
        {"failures": ["final_delivery_blocked_recovery_timeout"]},
        {"failures": ["final_delivery_blocked_recovery_timeout"]},
        {"failures": ["pdf_footer_overflow"]},
    ]

    report = build_self_harness_quality_report(outcomes=outcomes, min_recurrence=2)

    assert not report.ready
    assert report.score < 100
    assert report.status == "recurrent_failures_need_autopilot"
    assert report.timeout_failure_count == 2
    assert report.recurrent_failures == (
        {"signature": "final_delivery_blocked_recovery_timeout", "count": 2},
    )


def test_self_harness_quality_keeps_one_off_failures_observable() -> None:
    outcomes = [
        {"failures": ["pdf_footer_overflow"]},
        {"failures": []},
    ]

    report = build_self_harness_quality_report(outcomes=outcomes, min_recurrence=2)

    assert report.ready
    assert report.score == 99
    assert report.status == "one_off_failures_observed"
    assert report.top_failures == ({"signature": "pdf_footer_overflow", "count": 1},)


def test_self_harness_quality_scores_failures_after_active_baseline_only() -> None:
    outcomes = [
        {
            "created_at": "2026-06-26T10:00:00+00:00",
            "failures": ["reviewer_missing"],
        },
        {
            "created_at": "2026-06-26T10:05:00+00:00",
            "failures": ["reviewer_missing"],
        },
        {
            "created_at": "2026-06-26T15:00:00+00:00",
            "failures": [],
        },
    ]

    report = build_self_harness_quality_report(
        outcomes=outcomes,
        baseline_created_at="2026-06-26T14:55:24+00:00",
        min_recurrence=2,
    )

    assert report.ready
    assert report.score == 100
    assert report.status == "no_failures_since_baseline"
    assert report.historical_failure_count == 2
    assert report.to_payload()["baseline_created_at"] == "2026-06-26T14:55:24+00:00"


def test_self_harness_quality_closes_playbook_failures_after_followup_pass() -> None:
    outcomes = [
        {
            "created_at": "2026-06-27T10:00:00+00:00",
            "playbook_key": "academy_practical_recommendation",
            "review_status": "fail",
            "failures": ["reviewer_missing"],
        },
        {
            "created_at": "2026-06-27T10:01:00+00:00",
            "playbook_key": "academy_practical_recommendation",
            "review_status": "fail",
            "failures": ["reviewer_missing"],
        },
        {
            "created_at": "2026-06-27T10:05:00+00:00",
            "playbook_key": "academy_practical_recommendation",
            "review_status": "pass",
            "failures": [],
        },
    ]

    report = build_self_harness_quality_report(outcomes=outcomes, min_recurrence=2)

    assert report.ready
    assert report.score == 100
    assert report.failure_count == 0
    assert report.status == "failures_resolved_by_followup_pass"
    assert report.recurrent_failures == ()


def test_self_harness_quality_keeps_failures_after_latest_pass_open() -> None:
    outcomes = [
        {
            "created_at": "2026-06-27T10:00:00+00:00",
            "playbook_key": "academy_hakjong_report",
            "review_status": "pass",
            "failures": [],
        },
        {
            "created_at": "2026-06-27T10:05:00+00:00",
            "playbook_key": "academy_hakjong_report",
            "review_status": "fail",
            "failures": ["reviewer_missing"],
        },
        {
            "created_at": "2026-06-27T10:06:00+00:00",
            "playbook_key": "academy_hakjong_report",
            "review_status": "fail",
            "failures": ["reviewer_missing"],
        },
    ]

    report = build_self_harness_quality_report(outcomes=outcomes, min_recurrence=2)

    assert not report.ready
    assert report.status == "recurrent_failures_need_autopilot"
    assert report.recurrent_failures == ({"signature": "reviewer_missing", "count": 2},)
