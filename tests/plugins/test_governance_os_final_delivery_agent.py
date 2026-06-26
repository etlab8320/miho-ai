"""LLM Final Delivery Agent contract tests."""

from __future__ import annotations

import json
from typing import cast

from plugins.governance_os import final_delivery_agent


def _extract(response: object) -> str:
    assert isinstance(response, dict)
    typed = cast("dict[str, object]", response)
    return str(typed.get("content") or "")


def test_final_delivery_agent_revises_from_fenced_json() -> None:
    calls: list[dict[str, object]] = []

    def fake_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        payload = {
            "action": "revise",
            "answer": "# 미호 Governance OS 적대적 리뷰\nFinal Delivery Agent가 결과를 냅니다.",
        }
        return {"content": "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"}

    result = final_delivery_agent.review_final_delivery(
        question="미호 governance os 적대적 리뷰해줘",
        answer="확인 근거를 다시 모아 답변을 정리합니다.",
        evidence={"decision": {"reason": "internal_guard_leak"}},
        call_llm=fake_call_llm,
        extract_content=_extract,
    )

    assert result == "# 미호 Governance OS 적대적 리뷰\nFinal Delivery Agent가 결과를 냅니다."
    assert calls[0]["task"] == final_delivery_agent.FINAL_DELIVERY_TASK


def test_final_delivery_agent_rejects_internal_guard_answer() -> None:
    def fake_call_llm(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "content": json.dumps(
                {
                    "action": "revise",
                    "answer": "확인 근거를 다시 모아 답변을 정리합니다.",
                },
                ensure_ascii=False,
            )
        }

    result = final_delivery_agent.review_final_delivery(
        question="Q",
        answer="A",
        evidence={},
        call_llm=fake_call_llm,
        extract_content=_extract,
    )

    assert result is None


def test_final_delivery_agent_unavailable_does_not_generate_python_fallback() -> None:
    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("provider down")

    result = final_delivery_agent.review_final_delivery(
        question="Q",
        answer="A",
        evidence={},
        call_llm=boom,
        extract_content=_extract,
    )

    assert result is None
