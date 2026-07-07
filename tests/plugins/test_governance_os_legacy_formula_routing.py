"""Regression tests for previous-year Susi formula comparison routing."""

from __future__ import annotations

from plugins.governance_os.dispatcher import build_governance_rewrite, dispatch_request
from plugins.governance_os.registry import load_builtin_registry


def test_dispatch_request_selects_susi_legacy_formula_compare_playbook() -> None:
    decision = dispatch_request(
        load_builtin_registry(),
        "작년 대진대 입학처 수시 모집요강 PDF 보고 솔빈이 작년 산식으로 계산해봐",
        available_context=("student_identity", "target_university"),
    )

    assert decision.playbook_key == "susi_legacy_formula_compare"
    assert decision.required_tools == (
        "susi26_rule_lookup",
        "susi27_rule_lookup",
        "susi27_score_calculate",
        "web_search",
    )
    assert "student_subjects" in decision.missing_context
    assert decision.review_gates == ("academy_result_reviewer", "source_attribution_review")


def test_governance_rewrite_includes_success_contract_for_formula_compare() -> None:
    decision = dispatch_request(
        load_builtin_registry(),
        "작년 모집요강 PDF로 개인산식 비교해줘",
    )

    rewritten = build_governance_rewrite("작년 모집요강 PDF로 개인산식 비교해줘", decision)

    assert "작년 공식 모집요강 근거" in rewritten
    assert "계산표" in rewritten
    assert "pixel_document_evidence" not in rewritten
