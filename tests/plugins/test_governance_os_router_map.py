"""Agentic router-map tests for Governance OS dispatcher."""

from __future__ import annotations

import json

import pytest

from plugins.governance_os.dispatcher import (
    _call_auxiliary_dispatcher,
    _decision_from_auxiliary_payload,
    dispatch_request,
)
from plugins.governance_os.registry import load_builtin_registry
from plugins.governance_os.router_map import build_router_map


def test_router_map_covers_every_playbook_tool_contract() -> None:
    registry = load_builtin_registry()
    route_map = build_router_map(registry)
    contracts = route_map["tool_contracts"]
    expected = {
        tool
        for playbook in registry.playbooks.values()
        for tool in (*playbook.required_tools, *playbook.forbidden_tools)
    }

    assert sorted(expected - set(contracts)) == []
    for tool_name in expected:
        contract = contracts[tool_name]
        assert contract["contract_version"] == "tool-contract/v2"
        assert contract["purpose"]
        assert contract["output"]
        assert contract["reviewer"]
        assert contract["retry"]


def test_router_map_exposes_pdf_quality_gate_playbook_and_tool() -> None:
    route_map = build_router_map(load_builtin_registry())

    assert "designed_pdf_artifact" in route_map["playbooks"]
    playbook = route_map["playbooks"]["designed_pdf_artifact"]
    assert "html_pdf_quality_gate" in playbook["required_tools"]
    assert "media_delivery_contract" in playbook["required_tools"]
    assert "html_pdf_quality_gate" in route_map["tool_contracts"]
    assert "HTML-first" in route_map["tool_contracts"]["html_pdf_quality_gate"]["purpose"]
    assert route_map["tool_contracts"]["reportlab"]["kind"] == "blocked_capability"


@pytest.mark.asyncio
async def test_auxiliary_dispatcher_receives_full_router_map() -> None:
    calls: list[dict[str, object]] = []

    async def fake_call_llm(**kwargs: object) -> str:
        calls.append(kwargs)
        return json.dumps(
            {
                "playbook_key": "designed_pdf_artifact",
                "confidence": 0.94,
                "reason": "user wants a new designed PDF artifact",
                "matched_triggers": ["PDF로 줘"],
            },
            ensure_ascii=False,
        )

    registry = load_builtin_registry()
    decision = dispatch_request(registry, "방금 답변을 PDF로 줘")

    await _call_auxiliary_dispatcher(
        task="miho_governance_dispatcher",
        user_text="방금 답변을 PDF로 줘",
        deterministic_decision=decision,
        candidates=(),
        turn_context={"reply_to_text": "직전 답변 본문"},
        call_llm=fake_call_llm,
        extract_content=lambda value: value,
    )

    payload = json.loads(calls[0]["messages"][1]["content"])  # type: ignore[index]
    assert "route_map" in payload
    assert payload["turn_context"]["reply_to_text"] == "직전 답변 본문"
    assert "designed_pdf_artifact" in payload["route_map"]["playbooks"]
    assert "html_pdf_quality_gate" in payload["route_map"]["tool_contracts"]


def test_auxiliary_dispatcher_can_select_high_confidence_map_playbook() -> None:
    registry = load_builtin_registry()
    fallback = dispatch_request(registry, "수시 점수 계산 파일 첨부해서 보내줘")

    decision = _decision_from_auxiliary_payload(
        registry,
        {
            "playbook_key": "designed_pdf_artifact",
            "confidence": 0.94,
            "reason": "the user is asking for a designed PDF artifact",
            "matched_triggers": ["PDF로 줘"],
            "evidence": ["new artifact request"],
        },
        fallback=fallback,
        candidates=(),
    )

    assert decision is not None
    assert decision.playbook_key == "designed_pdf_artifact"
    assert decision.required_tools == ("html_pdf_quality_gate", "media_delivery_contract")
