"""Runtime readiness probes for Governance OS."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .registry import GovernanceRegistry
from .readiness_autonomy_probes import (
    final_delivery_repair_probe_passed as _final_delivery_repair_probe_passed,
    final_qa_repair_probe_passed as _final_qa_repair_probe_passed,
    self_harness_autonomy_probe_passed as _self_harness_autonomy_probe_passed,
)
from .readiness_plugin_probes import (
    auxiliary_dispatcher_dataplane_probe_passed as _auxiliary_dispatcher_dataplane_probe_passed,
    auxiliary_instruction_probe_passed as _auxiliary_instruction_probe_passed,
    auxiliary_reviewer_dataplane_probe_passed as _auxiliary_reviewer_dataplane_probe_passed,
    hook_probe_passed as _hook_probe_passed,
    manifest_probe_passed as _manifest_probe_passed,
    plugin_load_probe_passed as _plugin_load_probe_passed,
)


@dataclass(frozen=True)
class ReadinessProbeResults:
    council_probe_passed: bool
    risk_probe_passed: bool
    promotion_probe_passed: bool
    promotion_tests_probe_passed: bool
    retry_probe_passed: bool
    retry_instruction_probe_passed: bool
    transform_ledger_probe_passed: bool
    final_delivery_probe_passed: bool
    final_delivery_repair_probe_passed: bool
    final_qa_repair_probe_passed: bool
    self_harness_autonomy_probe_passed: bool
    evolution_rollback_probe_passed: bool
    hook_probe_passed: bool
    manifest_probe_passed: bool
    plugin_load_probe_passed: bool
    auxiliary_instruction_probe_passed: bool
    auxiliary_dispatcher_dataplane_probe_passed: bool
    auxiliary_reviewer_dataplane_probe_passed: bool
    failures: tuple[str, ...] = field(default_factory=tuple)


def run_readiness_probes(registry: GovernanceRegistry) -> ReadinessProbeResults:
    failures: list[str] = []
    council_probe_passed = _council_probe_passed(registry)
    if not council_probe_passed:
        failures.append("council probe did not reach review_required state")

    risk_probe_passed = _risk_probe_passed(registry)
    if not risk_probe_passed:
        failures.append("risk probe did not require approval for high-risk deploy request")

    promotion_probe_passed = _promotion_probe_passed()
    if not promotion_probe_passed:
        failures.append("promotion probe did not detect repeated ledger failures")

    promotion_tests_probe_passed = _promotion_tests_probe_passed()
    if not promotion_tests_probe_passed:
        failures.append("promotion required-tests probe did not enforce focused safety tests")

    retry_probe_passed = _retry_probe_passed(registry)
    if not retry_probe_passed:
        failures.append("retry probe did not return the required retry tool")

    retry_instruction_probe_passed = _retry_instruction_probe_passed()
    if not retry_instruction_probe_passed:
        failures.append("retry instruction probe did not expose safe retry guidance")

    transform_ledger_probe_passed = _transform_ledger_probe_passed()
    if not transform_ledger_probe_passed:
        failures.append("transform ledger probe did not capture self-reviewed tool outcomes")

    final_delivery_probe_passed = _final_delivery_probe_passed(registry)
    if not final_delivery_probe_passed:
        failures.append("final delivery probe did not block unreviewed governed output")

    final_delivery_repair_probe_passed = _final_delivery_repair_probe_passed()
    if not final_delivery_repair_probe_passed:
        failures.append("final delivery repair probe did not stage an allowed attachment")

    final_qa_repair_probe_passed = _final_qa_repair_probe_passed()
    if not final_qa_repair_probe_passed:
        failures.append("final QA repair probe did not reach LLM repair data-plane")

    self_harness_autonomy_probe_passed = _self_harness_autonomy_probe_passed()
    if not self_harness_autonomy_probe_passed:
        failures.append("self-harness autonomy probe did not activate and rollback")

    evolution_rollback_probe_passed = _evolution_rollback_probe_passed()
    if not evolution_rollback_probe_passed:
        failures.append("evolution rollback probe did not prove skill and harness rollback")

    hook_probe_passed = _hook_probe_passed()
    if not hook_probe_passed:
        failures.append("hook probe did not register required hooks and auxiliary tasks")

    manifest_probe_passed = _manifest_probe_passed()
    if not manifest_probe_passed:
        failures.append("manifest probe did not declare required hooks and auxiliary tasks")

    plugin_load_probe_passed = _plugin_load_probe_passed()
    if not plugin_load_probe_passed:
        failures.append("plugin load probe did not load required hooks and auxiliary tasks")

    auxiliary_instruction_probe_passed = _auxiliary_instruction_probe_passed()
    if not auxiliary_instruction_probe_passed:
        failures.append("auxiliary instruction probe did not find required judge guidance")

    auxiliary_dispatcher_dataplane_probe_passed = _auxiliary_dispatcher_dataplane_probe_passed(registry)
    if not auxiliary_dispatcher_dataplane_probe_passed:
        failures.append("auxiliary dispatcher data-plane probe did not find runtime call path")

    auxiliary_reviewer_dataplane_probe_passed = _auxiliary_reviewer_dataplane_probe_passed(registry)
    if not auxiliary_reviewer_dataplane_probe_passed:
        failures.append("auxiliary reviewer data-plane probe did not find runtime call path")

    return ReadinessProbeResults(
        council_probe_passed=council_probe_passed,
        risk_probe_passed=risk_probe_passed,
        promotion_probe_passed=promotion_probe_passed,
        promotion_tests_probe_passed=promotion_tests_probe_passed,
        retry_probe_passed=retry_probe_passed,
        retry_instruction_probe_passed=retry_instruction_probe_passed,
        transform_ledger_probe_passed=transform_ledger_probe_passed,
        final_delivery_probe_passed=final_delivery_probe_passed,
        final_delivery_repair_probe_passed=final_delivery_repair_probe_passed,
        final_qa_repair_probe_passed=final_qa_repair_probe_passed,
        self_harness_autonomy_probe_passed=self_harness_autonomy_probe_passed,
        evolution_rollback_probe_passed=evolution_rollback_probe_passed,
        hook_probe_passed=hook_probe_passed,
        manifest_probe_passed=manifest_probe_passed,
        plugin_load_probe_passed=plugin_load_probe_passed,
        auxiliary_instruction_probe_passed=auxiliary_instruction_probe_passed,
        auxiliary_dispatcher_dataplane_probe_passed=auxiliary_dispatcher_dataplane_probe_passed,
        auxiliary_reviewer_dataplane_probe_passed=auxiliary_reviewer_dataplane_probe_passed,
        failures=tuple(failures),
    )


def _council_probe_passed(registry: GovernanceRegistry) -> bool:
    from .council import run_council_turn

    result = run_council_turn(
        registry=registry,
        request_id="readiness-probe",
        user_text="최신 입시 정책 조사해줘",
        available_context=("source_attribution", "date_sensitivity", "user_question"),
        tool_name="web_search",
        tool_result=None,
        record_ledger=False,
    )
    return result.status == "review_required" and result.playbook_key == "research_brief"


def _risk_probe_passed(registry: GovernanceRegistry) -> bool:
    from .risk import evaluate_request_risk

    result = evaluate_request_risk(
        registry,
        playbook_key="dev_code_update",
        user_text="프로덕션 배포하고 게이트웨이 재시작해줘",
        available_context=("repo_root", "tests_required", "rollback_plan"),
        tool_name="apply_patch",
    )
    return result.action == "require_approval" and result.reason == "approval_required"


def _promotion_probe_passed() -> bool:
    from .promotion import detect_promotion_candidates

    events = [
        {
            "id": 1,
            "metadata": {
                "governance_outcome": {
                    "request_id": "readiness-promotion-1",
                    "playbook_key": "discord_attachment_delivery",
                    "review_status": "fail",
                    "failures": ["reviewer_missing"],
                }
            },
        },
        {
            "id": 2,
            "metadata": {
                "governance_outcome": {
                    "request_id": "readiness-promotion-2",
                    "playbook_key": "discord_attachment_delivery",
                    "review_status": "fail",
                    "failures": ["reviewer_missing"],
                }
            },
        },
    ]
    candidates = detect_promotion_candidates(events, min_recurrence=2)
    return (
        len(candidates) == 1
        and candidates[0].playbook_key == "discord_attachment_delivery"
        and candidates[0].source_failure == "reviewer_missing"
    )


def _promotion_tests_probe_passed() -> bool:
    from .promotion import detect_promotion_candidates

    events = [
        _promotion_probe_event(1, "academy_hakjong_report", "forbidden_tool"),
        _promotion_probe_event(2, "academy_hakjong_report", "forbidden_tool"),
        _promotion_probe_event(3, "discord_attachment_delivery", "reviewer_missing"),
        _promotion_probe_event(4, "discord_attachment_delivery", "reviewer_missing"),
    ]
    candidates = detect_promotion_candidates(events, min_recurrence=2)
    tests_by_failure = {
        (candidate.playbook_key, candidate.source_failure): set(candidate.tests_required)
        for candidate in candidates
    }
    academy_tests = tests_by_failure.get(("academy_hakjong_report", "forbidden_tool"), set())
    discord_tests = tests_by_failure.get(
        ("discord_attachment_delivery", "reviewer_missing"),
        set(),
    )
    foundation = "tests/plugins/test_governance_os_foundation.py"
    return (
        _required_tests_present(
            academy_tests,
            {
                "tests/plugins/test_governance_os_policy.py",
                "tests/plugins/test_governance_os_drills.py",
                "tests/plugins/test_governance_os_promotion_activation.py",
                "tests/plugins/test_governance_os_versioning.py",
            },
        )
        and foundation not in academy_tests
        and _required_tests_present(
            discord_tests,
            {
                "tests/e2e/test_discord_governance_delivery.py",
                "tests/tools/test_media_delivery_contract_tool.py",
                "tests/plugins/test_governance_os_review_retry.py",
                "tests/plugins/test_governance_os_council.py",
                "tests/plugins/test_governance_os_promotion_activation.py",
                "tests/plugins/test_governance_os_versioning.py",
            },
        )
        and foundation not in discord_tests
    )


def _promotion_probe_event(event_id: int, playbook_key: str, failure: str) -> dict[str, object]:
    return {
        "id": event_id,
        "metadata": {
            "governance_outcome": {
                "request_id": f"readiness-promotion-tests-{event_id}",
                "playbook_key": playbook_key,
                "review_status": "fail",
                "failures": [failure],
            }
        },
    }


def _required_tests_present(actual: set[str], required: set[str]) -> bool:
    return required <= actual


def _retry_probe_passed(registry: GovernanceRegistry) -> bool:
    from .review import evaluate_review_gate

    outcome = evaluate_review_gate(
        registry,
        playbook_key="discord_attachment_delivery",
        tool_name="media_delivery_contract",
        result={"success": True, "artifact_path": "/tmp/report.mhtml"},
    )
    return outcome.status == "fail" and outcome.retry_tools == ("media_delivery_contract",)


def _retry_instruction_probe_passed() -> bool:
    from .result_transform import governance_transform_tool_result

    raw = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        result={"success": True, "artifact_path": "/tmp/report.mhtml"},
        governance_skip_ledger=True,
    )
    if not isinstance(raw, str):
        return False
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False
    review = payload.get("governance_review")
    if not isinstance(review, dict):
        return False
    return (
        payload.get("next_action") == "retry_required"
        and review.get("retry_tools") == ["media_delivery_contract"]
        and "retry_tools" not in str(review.get("retry_instruction_ko") or "")
        and "전용 도구" in str(review.get("retry_instruction_ko") or "")
        and "media_delivery_contract" not in str(payload.get("error") or "")
    )


def _transform_ledger_probe_passed() -> bool:
    from .ledger import OutcomeLedgerEntry
    from .result_transform import governance_transform_tool_result

    captured: list[OutcomeLedgerEntry] = []
    raw = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        result={"success": True, "artifact_path": "/tmp/report.mhtml"},
        tool_call_id="readiness-transform-ledger",
        duration_ms=5,
        governance_ledger_recorder=captured.append,
    )
    if not isinstance(raw, str) or len(captured) != 1:
        return False
    entry = captured[0]
    return (
        entry.request_id == "readiness-transform-ledger"
        and entry.playbook_key == "discord_attachment_delivery"
        and entry.tools_used == ("media_delivery_contract",)
        and entry.duration_ms == 5
        and entry.review_status == "fail"
        and entry.failures == ("reviewer_missing",)
        and entry.retry_tools == ("media_delivery_contract",)
        and entry.artifact_paths == ("/tmp/report.mhtml",)
    )


def _final_delivery_probe_passed(registry: GovernanceRegistry) -> bool:
    from .delivery_gate import evaluate_final_delivery, governance_transform_llm_output

    blocked = evaluate_final_delivery(
        registry,
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_text="서연이 수시 환산점수 계산해줘",
        outcomes=[],
    )
    passed = evaluate_final_delivery(
        registry,
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_text="서연이 수시 환산점수 계산해줘",
        outcomes=[
            {
                "playbook_key": "susi_score_calculation",
                "review_status": "pass",
                "tools_used": ["susi27_score_calculate"],
                "failures": [],
            }
        ],
    )
    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
    )
    return (
        blocked.action == "block"
        and blocked.reason == "review_evidence_missing"
        and passed.action == "allow"
        and transformed is not None
        and "확인 근거" in transformed
        and "후검증" not in transformed
        and "전용 도구" not in transformed
    )


def _evolution_rollback_probe_passed() -> bool:
    from .evolution_rollback_probe import run_evolution_rollback_probe

    return run_evolution_rollback_probe()
