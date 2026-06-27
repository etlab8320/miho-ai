"""Current-result copy tests for exhausted Final Delivery recovery."""

from __future__ import annotations

from plugins.governance_os.final_delivery_current_result import compose_current_result


def test_current_result_uses_playbook_contract_for_score_copy() -> None:
    text = compose_current_result(
        {
            "decision": {
                "playbook_key": "susi_score_calculation",
                "retry_tools": ["susi27_score_calculate"],
            }
        }
    )

    assert text == (
        "현재 결론: 확정 환산점수 없음.\n"
        "필요한 입력: 학생 교과 성적, 지원 대학/학과, 전형."
    )


def test_current_result_uses_playbook_contract_for_pdf_copy() -> None:
    text = compose_current_result(
        {
            "decision": {
                "playbook_key": "designed_pdf_artifact",
                "retry_tools": ["html_pdf_quality_gate", "media_delivery_contract"],
            }
        }
    )

    assert text == (
        "현재 결론: 확정 PDF 첨부본 없음.\n"
        "필요한 입력: 정리할 원문, HTML 원본, 시각 검수 결과."
    )
