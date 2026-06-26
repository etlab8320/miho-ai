"""Governance contract for retry-needed reviewer results."""

from __future__ import annotations

import json

from plugins.governance_os.registry import load_builtin_registry
from plugins.governance_os.result_transform import governance_transform_tool_result
from plugins.governance_os.review import evaluate_review_gate


def test_governance_review_gate_preserves_retry_needed_contract() -> None:
    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        result=json.dumps(
            {
                "ok": True,
                "reviewer": {
                    "name": "academy_result_reviewer",
                    "status": "retry_needed",
                    "checked": ["레이아웃", "산식"],
                    "warnings": ["근거 부족"],
                    "retry_tools": ["sports_pe_brain_evidence", "sports_motion_feedback"],
                    "retry_args": [{"tool": "sports_pe_brain_evidence", "args": {"exercise": "제멀"}}],
                    "retry_instruction_ko": "근거팩 검색 후 다시 실행해 주세요.",
                },
            },
            ensure_ascii=False,
        ),
    )

    assert outcome.status == "retry_needed"
    assert outcome.reason == "reviewer_retry_needed"
    assert outcome.retry_tools == ("sports_pe_brain_evidence", "sports_motion_feedback")
    assert outcome.retry_args[0]["tool"] == "sports_pe_brain_evidence"


def test_governance_transform_marks_retry_needed_as_provisional() -> None:
    transformed = governance_transform_tool_result(
        tool_name="academy_hakjong_report_package",
        result=json.dumps(
            {
                "ok": True,
                "reviewer": {
                    "name": "academy_result_reviewer",
                    "status": "retry_needed",
                    "checked": ["레이아웃", "산식"],
                    "retry_tools": ["sports_pe_brain_evidence", "sports_motion_feedback"],
                    "retry_args": [{"tool": "sports_pe_brain_evidence", "args": {"exercise": "제멀"}}],
                    "retry_instruction_ko": "근거팩 검색 후 다시 실행해 주세요.",
                },
            },
            ensure_ascii=False,
        ),
        governance_skip_ledger=True,
    )
    payload = json.loads(transformed or "{}")

    assert payload["next_action"] == "retry_required"
    assert payload["delivery_status"] == "provisional"
    assert payload["governance_review"]["status"] == "retry_needed"
    assert payload["governance_review"]["retry_args"][0]["tool"] == "sports_pe_brain_evidence"


def test_governance_transform_preserves_tool_repair_contract() -> None:
    raw = {
        "ok": False,
        "retry_required": True,
        "final_response_allowed": False,
        "message": "학종 리포트 내용 검증 실패.",
        "agent_instruction": "errors를 고쳐 같은 도구를 다시 호출하라.",
        "errors": ["student_stage가 비어 있다."],
    }

    transformed = governance_transform_tool_result(
        tool_name="academy_hakjong_report_package",
        result=json.dumps(raw, ensure_ascii=False),
        governance_skip_ledger=True,
    )

    assert transformed is None
