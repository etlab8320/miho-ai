"""Regression tests for Governance OS final-hook fail-closed behavior."""

from __future__ import annotations

import json
from typing import cast

from plugins.governance_os import delivery_gate


def _extract(response: object) -> str:
    assert isinstance(response, dict)
    typed = cast("dict[str, object]", response)
    return str(typed.get("content") or "")


def test_hook_exception_uses_semantic_agent_not_candidate_gate(monkeypatch) -> None:
    original = "서연이는 한국체대 교과전형 쪽으로 잡는 게 맞습니다."
    semantic_calls: list[dict[str, object]] = []
    delivery_calls: list[str] = []

    def broken_registry() -> object:
        raise RuntimeError("registry unavailable")

    def semantic_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        semantic_calls.append(kwargs)
        return {
            "content": json.dumps(
                {
                    "action": "block",
                    "reason": "subtle_recommendation_claim_without_evidence",
                    "playbook_key": "academy_practical_recommendation",
                    "retry_tools": ["academy_practical_reco_all_candidates"],
                },
                ensure_ascii=False,
            )
        }

    def final_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        task = str(kwargs.get("task") or "")
        delivery_calls.append(task)
        if task == "miho_governance_final_qa_repair":
            return {"content": "현재 결론: 확정 추천 산출물 없음.\n필요한 입력: 학생 기록, 지역, 전형."}
        if task == "miho_governance_final_qa":
            return {"content": "pass"}
        raise AssertionError(f"unexpected task: {task}")

    monkeypatch.setattr(delivery_gate, "load_runtime_registry", broken_registry)

    transformed = delivery_gate.governance_transform_llm_output(
        response_text=original,
        user_message="서연이 실기 추천해줘",
        governance_outcomes=[],
        semantic_delivery_call_llm=semantic_call_llm,
        semantic_delivery_extract_content=_extract,
        final_delivery_call_llm=final_call_llm,
        final_delivery_extract_content=_extract,
    )

    assert transformed
    assert transformed != original
    assert "한국체대" not in transformed
    assert semantic_calls
    assert semantic_calls[0]["task"] == "miho_governance_semantic_delivery_judge"
    assert delivery_calls == ["miho_governance_final_qa_repair", "miho_governance_final_qa"]
    assert "hook" not in transformed.casefold()
    assert "guard" not in transformed.casefold()
    assert "retry" not in transformed.casefold()


def test_hook_exception_keeps_plain_ungoverned_answer(monkeypatch) -> None:
    original = "오늘 회의 요약은 세 가지입니다."

    def broken_registry() -> object:
        raise RuntimeError("registry unavailable")

    semantic_calls: list[dict[str, object]] = []

    def semantic_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        semantic_calls.append(kwargs)
        return {
            "content": json.dumps(
                {
                    "action": "allow",
                    "reason": "plain_summary_answer",
                    "playbook_key": "",
                    "retry_tools": [],
                },
                ensure_ascii=False,
            )
        }

    monkeypatch.setattr(delivery_gate, "load_runtime_registry", broken_registry)

    transformed = delivery_gate.governance_transform_llm_output(
        response_text=original,
        user_message="회의 요약해줘",
        governance_outcomes=[],
        semantic_delivery_call_llm=semantic_call_llm,
        semantic_delivery_extract_content=_extract,
    )

    assert transformed is None
    assert semantic_calls
