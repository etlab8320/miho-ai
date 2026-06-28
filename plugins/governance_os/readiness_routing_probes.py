"""Readiness probe for Hermes/Decision Twin routing closure."""

from __future__ import annotations

import asyncio
import json

from .registry import GovernanceRegistry


def routing_loop_probe_passed(registry: GovernanceRegistry | None = None) -> bool:
    return (
        _decision_twin_directive_probe_passed()
        and _decision_twin_unknown_tool_probe_passed()
        and _governance_dispatcher_context_probe_passed(registry)
    )


def _decision_twin_directive_probe_passed() -> bool:
    from plugins.decision_twin.router import annotate_result_text, parse_decision_payload

    decision = parse_decision_payload(
        {
            "action": "route",
            "required_tool": "html_pdf_quality_gate",
            "intent": "상담자료 PDF 제작",
            "confidence": 0.95,
            "tool_instruction": "HTML-first 원본을 만들고 quality gate를 통과시킨다.",
        }
    )
    text = annotate_result_text("방금 내용을 PDF로 줘", decision)
    return (
        "라우팅 지시" in text
        and "필수 실행 도구: html_pdf_quality_gate" in text
        and "MUST use required_tool before final answer" in text
        and "HTML-first 원본" in text
        and "참고용" not in text
    )


def _decision_twin_unknown_tool_probe_passed() -> bool:
    from plugins.decision_twin.router import parse_decision_payload, should_route_decision

    decision = parse_decision_payload(
        {
            "action": "route",
            "required_tool": "unknown_tool_name",
            "confidence": 0.99,
        }
    )
    return should_route_decision(decision) is False


def _governance_dispatcher_context_probe_passed(registry: GovernanceRegistry | None) -> bool:
    from .dispatcher import _call_auxiliary_dispatcher, dispatch_request
    from .registry import load_builtin_registry

    async def fake_call_llm(**kwargs: object) -> str:
        calls.append(kwargs)
        return json.dumps(
            {
                "playbook_key": "designed_pdf_artifact",
                "confidence": 0.95,
                "reason": "reply context asks for a PDF artifact",
                "evidence": ["reply_to_text"],
            },
            ensure_ascii=False,
        )

    calls: list[dict[str, object]] = []
    registry = registry or load_builtin_registry()
    decision = dispatch_request(registry, "이거 정리해줘")
    try:
        asyncio.run(
            _call_auxiliary_dispatcher(
                task="miho_governance_dispatcher",
                user_text="이거 정리해줘",
                candidate_decision=decision,
                candidates=(),
                registry=registry,
                turn_context={"reply_to_text": "4개월 시즌 운동 프로그램 초안"},
                call_llm=fake_call_llm,
                extract_content=lambda value: value,
            )
        )
    except Exception:
        return False
    if not calls:
        return False
    payload = json.loads(str(calls[0]["messages"][1]["content"]))
    return (
        payload["turn_context"]["reply_to_text"] == "4개월 시즌 운동 프로그램 초안"
        and "route_map" in payload
        and "designed_pdf_artifact" in payload["route_map"]["playbooks"]
        and "html_pdf_quality_gate" in payload["route_map"]["tool_contracts"]
    )
