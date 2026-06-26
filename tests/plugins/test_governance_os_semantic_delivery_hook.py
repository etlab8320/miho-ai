"""Semantic Delivery Judge hook-level regression tests."""

from __future__ import annotations

import json
from typing import cast

from plugins.governance_os.delivery_gate import governance_transform_llm_output


def _extract(response: object) -> str:
    assert isinstance(response, dict)
    typed = cast("dict[str, object]", response)
    return str(typed.get("content") or "")


def test_semantic_judge_can_override_review_context_allow() -> None:
    semantic_calls: list[dict[str, object]] = []
    final_calls: list[dict[str, object]] = []

    def fake_semantic_call(*_args: object, **kwargs: object) -> dict[str, object]:
        semantic_calls.append(kwargs)
        return {
            "content": json.dumps(
                {
                    "action": "block",
                    "reason": "actual_student_score_claim",
                    "playbook_key": "susi_score_calculation",
                    "retry_tools": ["susi27_score_calculate"],
                },
                ensure_ascii=False,
            )
        }

    def fake_final_call(*_args: object, **kwargs: object) -> dict[str, object]:
        final_calls.append(kwargs)
        return {
            "content": json.dumps(
                {
                    "action": "revise",
                    "answer": "현재 결론: 검증된 수시 환산점수 산출물은 없습니다.",
                },
                ensure_ascii=False,
            )
        }

    transformed = governance_transform_llm_output(
        response_text="Governance OS 리뷰 결과입니다. 서연이 수시 환산점수는 947.3점입니다.",
        user_message="그럼 미호 governance os 적대적 리뷰해줘",
        governance_outcomes=[],
        semantic_delivery_call_llm=fake_semantic_call,
        semantic_delivery_extract_content=_extract,
        final_delivery_call_llm=fake_final_call,
        final_delivery_extract_content=_extract,
    )

    assert transformed == "현재 결론: 검증된 수시 환산점수 산출물은 없습니다."
    assert semantic_calls
    assert final_calls


def test_semantic_judge_reviews_pure_review_context_allow() -> None:
    semantic_calls: list[dict[str, object]] = []

    def fake_semantic_call(*_args: object, **kwargs: object) -> dict[str, object]:
        semantic_calls.append(kwargs)
        return {
            "content": json.dumps(
                {
                    "action": "block",
                    "reason": "review_context_was_misclassified",
                    "playbook_key": "academy_hakjong_report",
                    "retry_tools": ["academy_hakjong_report_package"],
                },
                ensure_ascii=False,
            )
        }

    def fake_final_call(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "content": json.dumps(
                {
                    "action": "revise",
                    "answer": "현재 결론: 학종 PDF 산출물 근거는 없습니다.",
                },
                ensure_ascii=False,
            )
        }

    transformed = governance_transform_llm_output(
        response_text=(
            "# Governance OS 리뷰\n"
            "학종 PDF와 수시 추천 흐름은 모두 완료된 산출물처럼 보이지만 "
            "실제 evidence는 없습니다."
        ),
        user_message="미호 governance os 적대적 리뷰해줘",
        governance_outcomes=[],
        semantic_delivery_call_llm=fake_semantic_call,
        semantic_delivery_extract_content=_extract,
        final_delivery_call_llm=fake_final_call,
        final_delivery_extract_content=_extract,
    )

    assert transformed == "현재 결론: 학종 PDF 산출물 근거는 없습니다."
    assert semantic_calls


def test_semantic_judge_reviews_non_result_deferral_in_hook() -> None:
    semantic_calls: list[dict[str, object]] = []

    def fake_semantic_call(*_args: object, **kwargs: object) -> dict[str, object]:
        semantic_calls.append(kwargs)
        return {
            "content": json.dumps(
                {
                    "action": "block",
                    "reason": "answer_waits_instead_of_answering",
                    "playbook_key": "academy_hakjong_report",
                    "retry_tools": ["academy_hakjong_report_package"],
                },
                ensure_ascii=False,
            )
        }

    def fake_final_call(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "content": json.dumps(
                {
                    "action": "revise",
                    "answer": "현재 결론: 대전대 학종 PDF 산출물은 아직 없습니다.",
                },
                ensure_ascii=False,
            )
        }

    transformed = governance_transform_llm_output(
        response_text="확인한 뒤 PDF로 전달하겠습니다.",
        user_message="동하 대전대 학종 리포트 pdf로 줘",
        governance_outcomes=[],
        semantic_delivery_call_llm=fake_semantic_call,
        semantic_delivery_extract_content=_extract,
        final_delivery_call_llm=fake_final_call,
        final_delivery_extract_content=_extract,
    )

    assert transformed == "현재 결론: 대전대 학종 PDF 산출물은 아직 없습니다."
    assert semantic_calls
    messages = semantic_calls[0]["messages"]
    assert "확인한 뒤 PDF로 전달하겠습니다." in str(messages)
