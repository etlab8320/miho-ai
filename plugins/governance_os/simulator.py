"""Deterministic Governance OS scenario simulator."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .dispatcher import dispatch_request
from .policy import evaluate_tool_call
from .registry import GovernanceRegistry
from .review import evaluate_review_gate
from .risk import evaluate_request_risk


@dataclass(frozen=True)
class SimulationCase:
    key: str
    user_text: str
    tool_name: str
    expected_playbook: str
    expected_policy_action: str
    expected_review_status: str
    expected_final_status: str
    tool_result: Any = None
    available_context: tuple[str, ...] = field(default_factory=tuple)
    tool_args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SimulationResult:
    key: str
    passed: bool
    playbook_key: str
    policy_action: str
    review_status: str
    final_status: str
    expected: str
    observed: str
    message: str = ""


def run_simulation_suite(registry: GovernanceRegistry) -> list[SimulationResult]:
    return [_run_case(registry, case) for case in _builtin_cases()]


def _run_case(registry: GovernanceRegistry, case: SimulationCase) -> SimulationResult:
    dispatch = dispatch_request(
        registry,
        case.user_text,
        available_context=case.available_context,
    )
    policy = evaluate_request_risk(
        registry,
        playbook_key=dispatch.playbook_key,
        user_text=case.user_text,
        available_context=case.available_context,
        tool_name=case.tool_name,
        args=case.tool_args,
    )
    if policy.action != "require_approval":
        policy = evaluate_tool_call(
            registry,
            playbook_key=dispatch.playbook_key,
            tool_name=case.tool_name,
            args=case.tool_args,
        )
    return _evaluate_case_result(registry, case, dispatch, policy)


def _evaluate_case_result(
    registry: GovernanceRegistry,
    case: SimulationCase,
    dispatch: Any,
    policy: Any,
) -> SimulationResult:
    review_status = "not_run"
    final_status = "allow"
    message = policy.message_ko
    if policy.action == "require_approval":
        final_status = "hold"
        review_status = "approval_required"
    elif policy.action == "block":
        final_status = "block"
        review_status = "blocked"
    elif policy.action == "review_required" and case.tool_result is None:
        final_status = "review_required"
    else:
        review = evaluate_review_gate(
            registry,
            playbook_key=dispatch.playbook_key,
            tool_name=case.tool_name,
            result=case.tool_result,
        )
        review_status = review.status
        message = review.message_ko
        if review.status == "pass":
            final_status = "deliver"
        elif review.status == "needs_human_review":
            final_status = "hold"
        else:
            final_status = "retry"

    expected = _signature(
        case.expected_playbook,
        case.expected_policy_action,
        case.expected_review_status,
        case.expected_final_status,
    )
    observed = _signature(
        dispatch.playbook_key,
        policy.action,
        review_status,
        final_status,
    )
    return SimulationResult(
        key=case.key,
        passed=expected == observed,
        playbook_key=dispatch.playbook_key,
        policy_action=policy.action,
        review_status=review_status,
        final_status=final_status,
        expected=expected,
        observed=observed,
        message=message,
    )


def _builtin_cases() -> tuple[SimulationCase, ...]:
    return (
        SimulationCase(
            key="discord_attachment_success",
            user_text="mhtml 파일 첨부해서 보내줘",
            available_context=("media_tag", "artifact_path", "channel_permission"),
            tool_name="media_delivery_contract",
            tool_result=_reviewed_payload(
                "attachment_delivery_review",
                ("media_tag", "artifact_path"),
            ),
            expected_playbook="discord_attachment_delivery",
            expected_policy_action="review_required",
            expected_review_status="pass",
            expected_final_status="deliver",
        ),
        SimulationCase(
            key="discord_attachment_missing_reviewer_retry",
            user_text="엑셀 첨부가 안돼",
            tool_name="media_delivery_contract",
            tool_result={"success": True, "artifact_path": "/tmp/report.xlsx"},
            expected_playbook="discord_attachment_delivery",
            expected_policy_action="review_required",
            expected_review_status="fail",
            expected_final_status="retry",
        ),
        SimulationCase(
            key="academy_manual_pdf_block",
            user_text="서연이 학종 리포트 PDF 만들어줘",
            tool_name="write_file",
            tool_result={"success": True},
            expected_playbook="academy_hakjong_report",
            expected_policy_action="block",
            expected_review_status="blocked",
            expected_final_status="block",
        ),
        SimulationCase(
            key="practical_reco_missing_reviewer_retry",
            user_text="서연이 실기 추천 PDF 만들어줘",
            available_context=("student_score", "region", "admission_year"),
            tool_name="academy_practical_reco_package",
            tool_result={"success": True, "file_path": "/tmp/practical.pdf"},
            expected_playbook="academy_practical_recommendation",
            expected_policy_action="review_required",
            expected_review_status="fail",
            expected_final_status="retry",
        ),
        SimulationCase(
            key="susi_manual_score_block",
            user_text="체대 수시 추천 환산점수 직접 계산해줘",
            tool_name="terminal",
            tool_args={"command": "수시 환산점수를 직접 계산해서 추천표를 만들어줘"},
            expected_playbook="susi_score_calculation",
            expected_policy_action="block",
            expected_review_status="blocked",
            expected_final_status="block",
        ),
        SimulationCase(
            key="susi_score_calculation_missing_reviewer_retry",
            user_text="수시 환산점수 계산해줘",
            available_context=("student_subjects", "target_university", "admission_track"),
            tool_name="susi27_score_calculate",
            tool_result={"status": "calculated", "student_record_score": 947.3},
            expected_playbook="susi_score_calculation",
            expected_policy_action="review_required",
            expected_review_status="fail",
            expected_final_status="retry",
        ),
        SimulationCase(
            key="life_record_needs_human_review_hold",
            user_text="생기부 저장해줘",
            available_context=("student_identity", "source_file"),
            tool_name="life_record_ingest_pdf",
            tool_result=json.dumps(
                {
                    "success": True,
                    "reviewer": {
                        "name": "academy_result_reviewer",
                        "status": "needs_human_review",
                        "checked": ["생기부 검수 상태", "사람 검수 필요 여부"],
                    },
                },
                ensure_ascii=False,
            ),
            expected_playbook="life_record_ingest",
            expected_policy_action="review_required",
            expected_review_status="needs_human_review",
            expected_final_status="hold",
        ),
        SimulationCase(
            key="dev_deploy_requires_approval",
            user_text="프로덕션 배포하고 게이트웨이 재시작해줘",
            available_context=("repo_root", "tests_required", "rollback_plan"),
            tool_name="apply_patch",
            expected_playbook="dev_code_update",
            expected_policy_action="require_approval",
            expected_review_status="approval_required",
            expected_final_status="hold",
        ),
        SimulationCase(
            key="research_source_review_success",
            user_text="최신 입시 정책 조사해줘",
            available_context=("source_attribution", "date_sensitivity", "user_question"),
            tool_name="web_search",
            tool_result=_reviewed_payload("source_attribution_review", ("source_attribution",)),
            expected_playbook="research_brief",
            expected_policy_action="review_required",
            expected_review_status="pass",
            expected_final_status="deliver",
        ),
        SimulationCase(
            key="memory_privacy_missing_retry",
            user_text="앞으로는 상담 리포트는 짧게 써줘",
            tool_name="memory",
            tool_result=_reviewed_payload("memory_promotion_review", ("evidence",)),
            expected_playbook="memory_policy_update",
            expected_policy_action="review_required",
            expected_review_status="fail",
            expected_final_status="retry",
        ),
    )


def _reviewed_payload(name: str, checked: tuple[str, ...]) -> str:
    return json.dumps(
        {
            "success": True,
            "reviewer": {
                "name": name,
                "status": "pass",
                "checked": list(checked),
            },
        }
    )


def _signature(playbook: str, policy: str, review: str, final: str) -> str:
    return f"{playbook}:{policy}:{review}:{final}"
