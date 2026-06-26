"""Agent-first final delivery coverage for Governance OS."""

from __future__ import annotations

import json
from typing import Any, cast

from plugins.governance_os.delivery_gate import governance_transform_llm_output


def _extract(response: object) -> str:
    assert isinstance(response, dict)
    typed = cast("dict[str, object]", response)
    return str(typed.get("content") or "")


def test_allowed_answer_still_runs_universal_final_delivery_agent() -> None:
    calls: list[dict[str, Any]] = []

    def fake_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"content": json.dumps({"action": "deliver", "answer": "일반 답변입니다."})}

    transformed = governance_transform_llm_output(
        response_text="일반 답변입니다.",
        user_message="간단히 설명해줘",
        platform="discord",
        final_delivery_call_llm=fake_call_llm,
        final_delivery_extract_content=_extract,
    )

    assert transformed is None
    assert calls
    assert calls[0]["task"] == "miho_governance_final_delivery"
    evidence = json.loads(calls[0]["messages"][1]["content"].split("EVIDENCE: ", 1)[1])
    assert evidence["decision"]["action"] == "allow"
    assert evidence["final_delivery_agent_scope"] == "universal"
    assert evidence["python_semantic_decision_is_advisory"] is True


def test_meta_review_false_positive_is_resolved_by_final_delivery_agent() -> None:
    calls: list[dict[str, Any]] = []

    def fake_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "content": json.dumps(
                {
                    "action": "revise",
                    "answer": (
                        "미호 Governance OS 적대적 리뷰 결과입니다.\n"
                        "Final Delivery Agent는 결과 본문을 유지해야 합니다."
                    ),
                },
                ensure_ascii=False,
            )
        }

    transformed = governance_transform_llm_output(
        response_text=(
            "확인 근거를 다시 모아 답변을 정리합니다. "
            "수시/학종/첨부/점수 문맥 때문에 결과가 막힐 수 있습니다."
        ),
        user_message="미호 Governance OS + Self-Harness 적대적 리뷰해줘",
        platform="discord",
        final_delivery_call_llm=fake_call_llm,
        final_delivery_extract_content=_extract,
    )

    assert transformed is not None
    assert "적대적 리뷰 결과" in transformed
    assert "확인 근거를 다시 모아" not in transformed
    assert calls


def test_blocked_answer_fail_closes_when_all_delivery_agents_fail() -> None:
    def broken_call_llm(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("provider down")

    original = "서연이 수시 환산점수는 947.3점입니다."
    transformed = governance_transform_llm_output(
        response_text=original,
        user_message="서연이 수시 환산점수 계산해줘",
        platform="discord",
        governance_outcomes=[],
        final_delivery_call_llm=broken_call_llm,
        final_delivery_extract_content=_extract,
    )

    assert transformed is not None
    assert transformed != original
    assert "947.3" not in transformed
    assert "후검증" not in transformed
    assert "전용 도구" not in transformed
    assert "retry_tools" not in transformed
