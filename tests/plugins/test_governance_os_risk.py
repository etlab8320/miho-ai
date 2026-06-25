"""Risk judge tests for Governance OS."""

from __future__ import annotations

from plugins.governance_os.registry import load_builtin_registry
from plugins.governance_os.risk import evaluate_request_risk


def test_risk_judge_requires_approval_for_deployment_request() -> None:
    decision = evaluate_request_risk(
        load_builtin_registry(),
        playbook_key="dev_code_update",
        user_text="프로덕션 배포하고 게이트웨이 재시작해줘",
        available_context=("repo_root", "tests_required", "rollback_plan"),
        tool_name="apply_patch",
    )

    assert decision.action == "require_approval"
    assert decision.reason == "approval_required"
    assert decision.agent_key == "risk_judge"
    assert "승인" in decision.message_ko
    assert "Traceback" not in decision.message_ko
    assert "CORS" not in decision.message_ko


def test_risk_judge_allows_low_risk_reviewed_research_request() -> None:
    decision = evaluate_request_risk(
        load_builtin_registry(),
        playbook_key="research_brief",
        user_text="최신 입시 정책 조사해줘",
        available_context=("source_attribution", "date_sensitivity", "user_question"),
        tool_name="web_search",
    )

    assert decision.action == "allow"
    assert decision.reason == "risk_accepted"
