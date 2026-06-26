"""Decision Twin routing coverage for new HTML-first PDF artifacts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.decision_twin import _decision_twin_pre_gateway_dispatch
from plugins.decision_twin.contracts import decision_tool_contracts
from plugins.decision_twin.router import build_decision_messages


def _event(text: str) -> MessageEvent:
    return MessageEvent(
        text=text,
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="u1",
            chat_id="channel-1",
            guild_id="guild-1",
        ),
    )


def test_pdf_quality_gate_contract_is_available_to_llm_router() -> None:
    contracts = decision_tool_contracts()

    contract = contracts["html_pdf_quality_gate"]
    assert contract["domain"] == "artifact"
    assert "HTML-first" in contract["purpose"]
    assert "PyMuPDF" in contract["purpose"]
    assert "ReportLab" in contract["purpose"]


def test_decision_prompt_routes_new_pdf_artifacts_to_quality_gate() -> None:
    messages = build_decision_messages(
        user_text="방금 말한 4개월 시즌 운동 프로그램 PDF로 줘",
        turn_context={"reply_to_text": "4개월 시즌 운동 프로그램 초안"},
    )
    joined = "\n".join(message["content"] for message in messages)

    assert "html_pdf_quality_gate" in joined
    assert "HTML-first" in joined
    assert "PDF를 처음부터 요청" in joined
    assert "PyMuPDF" in joined


@pytest.mark.asyncio
async def test_decision_twin_rewrites_initial_pdf_request_to_quality_gate() -> None:
    async def resolver(_messages):
        return {
            "action": "route",
            "route": "academy_ops",
            "intent": "이전 답변을 상담용 PDF로 제작",
            "required_tool": "html_pdf_quality_gate",
            "confidence": 0.94,
            "evidence": ["사용자가 PDF 제작을 처음부터 요청했다"],
            "tool_instruction": (
                "자체 포함 HTML을 만든 뒤 html_pdf_quality_gate를 호출하고 "
                "통과 PDF만 media_delivery_contract로 전달한다."
            ),
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("AI 티 안 나게 정리해서 PDF로 줘"),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
        owner_context_builder=lambda _text: "",
    )

    assert result["action"] == "rewrite"
    assert result["required_tool"] == "html_pdf_quality_gate"
    assert "html_pdf_quality_gate" in str(result["text"])
