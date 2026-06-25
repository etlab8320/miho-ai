"""Deterministic Governance OS drills."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .guard import governance_pre_tool_call
from .policy import evaluate_tool_call
from .promotion import PromotionCandidate, validate_candidate
from .registry import GovernanceRegistry
from .review import evaluate_review_gate


@dataclass(frozen=True)
class DrillResult:
    key: str
    passed: bool
    expected: str
    observed: str
    message: str = ""


def run_builtin_drills(registry: GovernanceRegistry) -> list[DrillResult]:
    return [
        _manual_pdf_block_drill(),
        _required_tool_review_drill(registry),
        _practical_reco_review_drill(registry),
        _susi_manual_score_block_drill(),
        _susi_score_calculation_review_drill(registry),
        _life_record_ingest_review_drill(registry),
        _missing_reviewer_drill(registry),
        _dev_destructive_git_block_drill(registry),
        _research_search_review_drill(registry),
        _discord_attachment_review_drill(registry),
        _memory_policy_review_drill(registry),
        _promotion_candidate_requires_rollback_drill(),
    ]


def _manual_pdf_block_drill() -> DrillResult:
    result = governance_pre_tool_call(
        tool_name="write_file",
        args={"path": "report.pdf", "content": "가은이 학종 리포트 PDF를 직접 만들어줘"},
    )
    observed = str((result or {}).get("action") or "allow")
    return DrillResult(
        key="hakjong_manual_pdf_block",
        passed=observed == "block",
        expected="block",
        observed=observed,
        message=str((result or {}).get("message") or ""),
    )


def _required_tool_review_drill(registry: GovernanceRegistry) -> DrillResult:
    decision = evaluate_tool_call(
        registry,
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        args={"student_name": "가은"},
    )
    return DrillResult(
        key="hakjong_required_tool_review_required",
        passed=decision.action == "review_required",
        expected="review_required",
        observed=decision.action,
        message=decision.message_ko,
    )


def _practical_reco_review_drill(registry: GovernanceRegistry) -> DrillResult:
    decision = evaluate_tool_call(
        registry,
        playbook_key="academy_practical_recommendation",
        tool_name="academy_practical_reco_package",
        args={"student_name": "서연"},
    )
    return DrillResult(
        key="practical_reco_required_tool_review_required",
        passed=decision.action == "review_required",
        expected="review_required",
        observed=decision.action,
        message=decision.message_ko,
    )


def _susi_manual_score_block_drill() -> DrillResult:
    result = governance_pre_tool_call(
        tool_name="terminal",
        args={"command": "체대 수시 추천 환산점수를 직접 계산해서 PDF로 만들어줘"},
    )
    observed = str((result or {}).get("action") or "allow")
    return DrillResult(
        key="susi_manual_score_block",
        passed=observed == "block",
        expected="block",
        observed=observed,
        message=str((result or {}).get("message") or ""),
    )


def _susi_score_calculation_review_drill(registry: GovernanceRegistry) -> DrillResult:
    decision = evaluate_tool_call(
        registry,
        playbook_key="susi_score_calculation",
        tool_name="susi27_score_calculate",
        args={"student_name": "서연", "target_university": "서경대"},
    )
    return DrillResult(
        key="susi_score_calculation_review_required",
        passed=decision.action == "review_required",
        expected="review_required",
        observed=decision.action,
        message=decision.message_ko,
    )


def _life_record_ingest_review_drill(registry: GovernanceRegistry) -> DrillResult:
    decision = evaluate_tool_call(
        registry,
        playbook_key="life_record_ingest",
        tool_name="life_record_ingest_pdf",
        args={"pdf_path": "/tmp/record.mhtml"},
    )
    return DrillResult(
        key="life_record_ingest_review_required",
        passed=decision.action == "review_required",
        expected="review_required",
        observed=decision.action,
        message=decision.message_ko,
    )


def _missing_reviewer_drill(registry: GovernanceRegistry) -> DrillResult:
    outcome = evaluate_review_gate(
        registry,
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        result=json.dumps({"ok": True, "file_path": "/tmp/report.pdf"}),
    )
    return DrillResult(
        key="hakjong_missing_reviewer_fail",
        passed=outcome.status == "fail" and outcome.reason == "reviewer_missing",
        expected="fail:reviewer_missing",
        observed=f"{outcome.status}:{outcome.reason}",
        message=outcome.message_ko,
    )


def _dev_destructive_git_block_drill(registry: GovernanceRegistry) -> DrillResult:
    decision = evaluate_tool_call(
        registry,
        playbook_key="dev_code_update",
        tool_name="terminal",
        args={"command": "git reset --hard"},
    )
    return DrillResult(
        key="dev_destructive_git_block",
        passed=decision.action == "block",
        expected="block",
        observed=decision.action,
        message=decision.message_ko,
    )


def _research_search_review_drill(registry: GovernanceRegistry) -> DrillResult:
    decision = evaluate_tool_call(
        registry,
        playbook_key="research_brief",
        tool_name="web_search",
        args={"query": "latest admissions policy"},
    )
    return DrillResult(
        key="research_search_review_required",
        passed=decision.action == "review_required",
        expected="review_required",
        observed=decision.action,
        message=decision.message_ko,
    )


def _discord_attachment_review_drill(registry: GovernanceRegistry) -> DrillResult:
    decision = evaluate_tool_call(
        registry,
        playbook_key="discord_attachment_delivery",
        tool_name="media_delivery_contract",
        args={"artifact_path": "/tmp/report.pdf"},
    )
    return DrillResult(
        key="discord_attachment_review_required",
        passed=decision.action == "review_required",
        expected="review_required",
        observed=decision.action,
        message=decision.message_ko,
    )


def _memory_policy_review_drill(registry: GovernanceRegistry) -> DrillResult:
    decision = evaluate_tool_call(
        registry,
        playbook_key="memory_policy_update",
        tool_name="memory",
        args={"action": "add", "target": "user", "content": "앞으로 답변은 한국어로 해줘"},
    )
    return DrillResult(
        key="memory_policy_review_required",
        passed=decision.action == "review_required",
        expected="review_required",
        observed=decision.action,
        message=decision.message_ko,
    )


def _promotion_candidate_requires_rollback_drill() -> DrillResult:
    candidate = PromotionCandidate(
        playbook_key="academy_hakjong_report",
        source_failure="manual PDF bypass repeated",
        recurrence_count=2,
        proposed_policy="block direct file generation",
        evidence=("failure-1", "failure-2"),
        tests_required=("test_guard_blocks_manual_pdf",),
        rollback="",
    )
    errors = validate_candidate(candidate)
    passed = "rollback is required" in errors
    return DrillResult(
        key="promotion_candidate_requires_rollback",
        passed=passed,
        expected="rollback is required",
        observed="; ".join(errors),
    )
