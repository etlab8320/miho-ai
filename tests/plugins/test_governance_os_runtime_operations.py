"""Runtime deployment preflight checks for Governance OS."""

from __future__ import annotations

from plugins.governance_os.deployment_preflight import (
    build_verification_receipt,
    run_deployment_preflight,
)


def _passing_receipt(name: str) -> dict[str, object]:
    return build_verification_receipt(
        name=name,
        command=f"run {name}",
        evidence=f"{name} passed",
    )


def _fabricated_receipt(name: str) -> dict[str, object]:
    return {
        "name": name,
        "status": "passed",
        "exit_code": 0,
        "command": f"run {name}",
        "evidence": f"{name} passed",
    }


def test_deployment_preflight_blocks_restart_without_required_receipts() -> None:
    report = run_deployment_preflight(
        target="gateway_restart",
        test_receipts=[],
        smoke_receipts=[],
        config_checks=[],
        rollback_plan="",
    )

    assert not report.ready
    assert report.readiness_ready
    assert report.readiness_quality_score == 100
    assert not report.tests_passed
    assert not report.smoke_passed
    assert not report.config_passed
    assert not report.rollback_plan_passed
    assert "missing test receipts: related_governance_suite, static_checks" in report.failures
    assert "missing smoke receipts: governance_status, discord_delivery" in report.failures
    assert "missing config checks: gateway_service_definition" in report.failures
    assert "rollback plan is required" in report.failures


def test_deployment_preflight_passes_with_local_verified_receipts() -> None:
    report = run_deployment_preflight(
        target="gateway_restart",
        test_receipts=[
            _passing_receipt("related_governance_suite"),
            _passing_receipt("static_checks"),
        ],
        smoke_receipts=[
            _passing_receipt("governance_status"),
            _passing_receipt("discord_delivery"),
        ],
        config_checks=[_passing_receipt("gateway_service_definition")],
        rollback_plan="Use the previous launchd service state and revert this diff before another restart.",
    )

    assert report.ready
    assert report.tests_passed
    assert report.smoke_passed
    assert report.config_passed
    assert report.rollback_plan_passed
    assert report.failures == ()
    assert report.required_test_receipts == ("related_governance_suite", "static_checks")
    assert report.required_smoke_receipts == ("governance_status", "discord_delivery")


def test_deployment_preflight_rejects_fabricated_status_only_receipts() -> None:
    report = run_deployment_preflight(
        target="gateway_restart",
        test_receipts=[
            _fabricated_receipt("related_governance_suite"),
            _fabricated_receipt("static_checks"),
        ],
        smoke_receipts=[
            _fabricated_receipt("governance_status"),
            _fabricated_receipt("discord_delivery"),
        ],
        config_checks=[_fabricated_receipt("gateway_service_definition")],
        rollback_plan="Rollback to previous gateway process and revert the change if smoke fails.",
    )

    assert not report.ready
    assert not report.tests_passed
    assert "invalid test receipts: 2" in report.failures
    assert "invalid smoke receipts: 2" in report.failures
    assert "invalid config checks: 1" in report.failures


def test_deployment_preflight_rejects_string_only_test_claims() -> None:
    report = run_deployment_preflight(
        target="gateway_restart",
        test_receipts=["tests passed"],
        smoke_receipts=[
            _passing_receipt("governance_status"),
            _passing_receipt("discord_delivery"),
        ],
        config_checks=[_passing_receipt("gateway_service_definition")],
        rollback_plan="Rollback to previous gateway process and revert the change if smoke fails.",
    )

    assert not report.ready
    assert not report.tests_passed
    assert "invalid test receipts: 1" in report.failures
    assert "missing test receipts: related_governance_suite, static_checks" in report.failures
