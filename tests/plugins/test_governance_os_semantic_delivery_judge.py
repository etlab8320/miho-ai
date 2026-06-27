"""Semantic Delivery Judge contract tests."""

from __future__ import annotations

import json
from typing import Any, cast

from plugins.governance_os import semantic_delivery_judge


def _extract(response: object) -> str:
    assert isinstance(response, dict)
    typed = cast("dict[str, object]", response)
    return str(typed.get("content") or "")


def test_semantic_delivery_judge_parses_fenced_json_allow() -> None:
    calls: list[dict[str, Any]] = []

    def fake_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        payload = {
            "action": "allow",
            "reason": "quoted_review_example",
            "playbook_key": "",
            "retry_tools": [],
        }
        return {"content": "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"}

    verdict = semantic_delivery_judge.judge_delivery_semantics(
        question="미호 거버넌스 적대적 리뷰해줘",
        answer="예시 점수 문구는 리뷰 문맥입니다.",
        evidence={"runtime_semantic_signal_is_advisory": True},
        call_llm=fake_call_llm,
        extract_content=_extract,
    )

    assert verdict is not None
    assert verdict.action == "allow"
    assert verdict.reason == "quoted_review_example"
    assert calls[0]["task"] == semantic_delivery_judge.SEMANTIC_DELIVERY_JUDGE_TASK


def test_semantic_delivery_judge_uses_default_auxiliary_client(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "content": json.dumps(
                {
                    "action": "block",
                    "reason": "subtle_claim_without_review",
                    "playbook_key": "academy_practical_recommendation",
                    "retry_tools": ["academy_practical_reco_all_candidates"],
                },
                ensure_ascii=False,
            )
        }

    monkeypatch.setattr(semantic_delivery_judge, "_running_under_pytest", lambda: False)
    monkeypatch.setattr("agent.auxiliary_client.call_llm", fake_call_llm)
    monkeypatch.setattr("agent.auxiliary_client.extract_content_or_reasoning", _extract)

    verdict = semantic_delivery_judge.judge_delivery_semantics(
        question="서연이 실기 추천해줘",
        answer="서연이는 한국체대 교과전형 쪽으로 잡는 게 맞습니다.",
        evidence={"runtime_semantic_signal_is_advisory": True},
    )

    assert verdict is not None
    assert verdict.action == "block"
    assert verdict.retry_tools == ("academy_practical_reco_all_candidates",)
    assert calls[0]["task"] == semantic_delivery_judge.SEMANTIC_DELIVERY_JUDGE_TASK


def test_semantic_delivery_judge_abstains_on_internal_guard_leak() -> None:
    def fake_call_llm(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("internal guard leak must not call semantic judge")

    verdict = semantic_delivery_judge.judge_delivery_semantics(
        question="학종 리포트 줘",
        answer="후검증을 통과하지 못했습니다. 전용 도구를 다시 실행해야 합니다.",
        evidence={},
        call_llm=fake_call_llm,
        extract_content=_extract,
    )

    assert verdict is None


def test_semantic_delivery_judge_reviews_non_result_deferral() -> None:
    calls: list[dict[str, Any]] = []

    def fake_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
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

    verdict = semantic_delivery_judge.judge_delivery_semantics(
        question="동하 대전대 학종 리포트 pdf로 줘",
        answer="확인한 뒤 PDF로 전달하겠습니다.",
        evidence={"runtime_semantic_signal_is_advisory": True},
        call_llm=fake_call_llm,
        extract_content=_extract,
    )

    assert verdict is not None
    assert verdict.action == "block"
    assert verdict.reason == "answer_waits_instead_of_answering"
    assert calls[0]["task"] == semantic_delivery_judge.SEMANTIC_DELIVERY_JUDGE_TASK
