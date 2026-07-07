"""System WikiGraph delivery regressions for Governance OS."""

from __future__ import annotations

import json
from typing import Any, cast

from plugins.governance_os import delivery_gate
from plugins.governance_os.delivery_gate import evaluate_final_delivery
from plugins.governance_os.delivery_semantic_flow import decision_from_semantic_verdict
from plugins.governance_os.registry import load_builtin_registry
from plugins.governance_os.semantic_delivery_judge import SemanticDeliveryVerdict


WIKIGRAPH_QUESTION = (
    "스킬/도구/크론/에이전트 관계 지도. 어떤 스킬이 어떤 도구를 쓰고, "
    "어떤 실패를 막는지 그래프로 보이면 거버넌스가 더 강해져. "
    "이거 이미 wiki llm 그래프 우리 있잖아 한번봐봐."
)
WIKIGRAPH_ANSWER = (
    "system_wiki와 system_graph/graph.db를 확인했습니다. "
    "현재 그래프에는 Skill 310개, Tool 174개, Test 1495개 노드가 있고, "
    "requires_test, validates, owned_by edge로 스킬/도구/테스트 관계를 볼 수 있습니다."
)


def _extract(response: object) -> str:
    assert isinstance(response, dict)
    typed = cast("dict[str, object]", response)
    return str(typed.get("content") or "")


def test_wikigraph_relationship_map_is_governance_meta_context() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text=WIKIGRAPH_ANSWER,
        user_text=WIKIGRAPH_QUESTION,
        outcomes=[],
    )

    assert decision.action == "allow"
    assert decision.reason == "governance_review_context"


def test_unknown_semantic_playbook_cannot_block_ungoverned_answer() -> None:
    original = delivery_gate.FinalDeliveryDecision(
        action="allow",
        reason="governance_review_context",
    )
    verdict = SemanticDeliveryVerdict(
        action="block",
        reason="hallucinated_attachment_claim",
        playbook_key="unsupported_attachment_delivery_claim",
        retry_tools=("unsupported_attachment_delivery_claim",),
    )

    decision = decision_from_semantic_verdict(
        original,
        verdict,
        decision_factory=delivery_gate.FinalDeliveryDecision,
        known_playbooks=frozenset(load_builtin_registry().playbooks),
    )

    assert decision is original


def test_hook_exception_keeps_system_wikigraph_answer(monkeypatch) -> None:
    semantic_calls: list[dict[str, Any]] = []
    final_calls: list[dict[str, Any]] = []

    def broken_registry() -> object:
        raise KeyError("unsupported_attachment_delivery_claim")

    def semantic_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        semantic_calls.append(kwargs)
        return {
            "content": json.dumps(
                {
                    "action": "block",
                    "reason": "hallucinated_attachment_delivery",
                    "playbook_key": "unsupported_attachment_delivery_claim",
                    "retry_tools": ["unsupported_attachment_delivery_claim"],
                },
                ensure_ascii=False,
            )
        }

    def final_call_llm(*_args: object, **kwargs: object) -> object:
        final_calls.append(kwargs)
        raise TimeoutError("blocked recovery timeout")

    monkeypatch.setattr(delivery_gate, "load_runtime_registry", broken_registry)

    transformed = delivery_gate.governance_transform_llm_output(
        response_text=WIKIGRAPH_ANSWER,
        user_message=WIKIGRAPH_QUESTION,
        governance_outcomes=[],
        semantic_delivery_call_llm=semantic_call_llm,
        semantic_delivery_extract_content=_extract,
        final_delivery_call_llm=final_call_llm,
        final_delivery_extract_content=_extract,
    )

    assert transformed is None
    assert semantic_calls == []
    assert final_calls == []
