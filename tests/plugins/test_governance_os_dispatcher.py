"""Dispatcher contract tests for Governance OS playbook routing."""

from __future__ import annotations

import importlib
import json

import pytest

from plugins.governance_os.dispatcher import (
    build_governance_rewrite,
    dispatch_request,
    governance_pre_gateway_dispatch,
)
from plugins.governance_os.registry import load_builtin_registry


class _Source:
    user_id = "owner"


class _Event:
    source = _Source()

    def __init__(self, text: str, message_id: str = "msg-1") -> None:
        self.text = text
        self.message_id = message_id


class _Gateway:
    def _is_user_authorized(self, source: object) -> bool:
        return bool(source)


def _patch_auxiliary_route(
    monkeypatch,
    playbook_key: str,
    *,
    matched_triggers: tuple[str, ...] = (),
) -> None:
    import plugins.governance_os.dispatcher as dispatcher

    async def fake_auxiliary_dispatcher(**_: object) -> dict[str, object]:
        return {
            "playbook_key": playbook_key,
            "confidence": 0.95,
            "reason": "test LLM route",
            "matched_triggers": list(matched_triggers),
            "evidence": ["test_llm_route"],
        }

    monkeypatch.setattr(
        dispatcher,
        "_call_auxiliary_dispatcher",
        fake_auxiliary_dispatcher,
        raising=False,
    )


def test_dispatch_request_selects_hakjong_playbook_with_missing_context() -> None:
    decision = dispatch_request(
        load_builtin_registry(),
        "서연이 학종 리포트 PDF 만들어줘",
        available_context=("student_identity", "life_record_evidence"),
    )

    assert decision.playbook_key == "academy_hakjong_report"
    assert decision.confidence >= 0.75
    assert decision.required_tools == ("academy_hakjong_report_package",)
    assert decision.missing_context == ("requested_universities",)


def test_dispatch_request_selects_discord_attachment_playbook() -> None:
    decision = dispatch_request(load_builtin_registry(), "mhtml 파일 첨부가 안돼")

    assert decision.playbook_key == "discord_attachment_delivery"
    assert decision.required_tools == ("media_delivery_contract",)
    assert "mhtml 첨부" in decision.matched_triggers


def test_dispatch_request_selects_susi_score_calculation_playbook() -> None:
    decision = dispatch_request(
        load_builtin_registry(),
        "서연이 수시 점수 계산하고 내신 환산 해줘",
        available_context=("student_subjects",),
    )

    assert decision.playbook_key == "susi_score_calculation"
    assert decision.required_tools == ("susi27_score_calculate",)
    assert decision.review_gates == ("academy_result_reviewer",)
    assert decision.missing_context == ("target_university", "admission_track")


def test_dispatch_request_allows_unmatched_text() -> None:
    decision = dispatch_request(load_builtin_registry(), "오늘 점심 뭐 먹지")

    assert decision.playbook_key == ""
    assert decision.confidence == 0.0
    assert decision.action == "allow"


def test_governance_rewrite_preserves_original_text() -> None:
    decision = dispatch_request(load_builtin_registry(), "최신 입시 정책 조사해줘")

    rewritten = build_governance_rewrite("최신 입시 정책 조사해줘", decision)

    assert rewritten.startswith("최신 입시 정책 조사해줘")
    assert "research_brief" in rewritten
    assert "web_search" in rewritten


def test_governance_rewrite_instructs_required_tool_before_delivery() -> None:
    decision = dispatch_request(load_builtin_registry(), "mhtml 파일 첨부해서 보내줘")

    rewritten = build_governance_rewrite("mhtml 파일 첨부해서 보내줘", decision)

    assert "MUST use required_tools before final delivery" in rewritten
    assert "Do not handwrite MEDIA tags" in rewritten
    assert "media_delivery_contract" in rewritten


def test_governance_rewrite_requires_missing_context_resolution() -> None:
    decision = dispatch_request(
        load_builtin_registry(),
        "서연이 학종 리포트 PDF 만들어줘",
        available_context=("student_identity",),
    )

    rewritten = build_governance_rewrite("서연이 학종 리포트 PDF 만들어줘", decision)

    assert "requested_universities" in rewritten
    assert "life_record_evidence" in rewritten
    assert "MUST resolve missing_context before calling required_tools" in rewritten
    assert "Korean clarification" in rewritten


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_rewrites_authorized_high_confidence_request(
    monkeypatch,
) -> None:
    _patch_auxiliary_route(
        monkeypatch,
        "academy_practical_recommendation",
        matched_triggers=("실기 추천",),
    )

    result = await governance_pre_gateway_dispatch(
        event=_Event("실기 추천 PDF 만들어줘"),
        gateway=_Gateway(),
    )

    assert result["action"] == "rewrite"
    assert result["route"] == "governance_os"
    assert result["required_tool"] == "academy_practical_reco_package"
    assert result["missing_context"] == ["student_score", "region", "admission_year"]
    assert "실기 추천 PDF 만들어줘" in str(result["text"])


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_rewrites_susi_score_calculation_request(
    monkeypatch,
) -> None:
    _patch_auxiliary_route(
        monkeypatch,
        "susi_score_calculation",
        matched_triggers=("수시", "환산점수"),
    )

    result = await governance_pre_gateway_dispatch(
        event=_Event("수시 환산점수 계산해줘"),
        gateway=_Gateway(),
    )

    assert result["action"] == "rewrite"
    assert result["route"] == "governance_os"
    assert result["intent"] == "susi_score_calculation"
    assert result["required_tool"] == "susi27_score_calculate"
    assert "susi27_score_calculate" in str(result["text"])


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_holds_high_risk_request_for_approval(
    monkeypatch,
) -> None:
    _patch_auxiliary_route(
        monkeypatch,
        "dev_code_update",
        matched_triggers=("프로덕션 배포",),
    )

    result = await governance_pre_gateway_dispatch(
        event=_Event("프로덕션 배포하고 게이트웨이 재시작해줘"),
        gateway=_Gateway(),
    )

    assert result["action"] == "respond"
    assert result["route"] == "governance_os"
    assert result["intent"] == "dev_code_update"
    assert result["approval_required"] is True
    assert result["required_tool"] == ""
    assert "승인" in str(result["text"])
    assert "작업을 진행하지 않습니다" in str(result["text"])
    assert "approval_required" not in str(result["text"])


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_records_approval_hold_in_ledger(
    tmp_path,
    monkeypatch,
) -> None:
    _patch_auxiliary_route(
        monkeypatch,
        "dev_code_update",
        matched_triggers=("프로덕션 배포",),
    )
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants
    from agent import evolution

    importlib.reload(miho_constants)
    importlib.reload(evolution)

    await governance_pre_gateway_dispatch(
        event=_Event("프로덕션 배포하고 게이트웨이 재시작해줘", message_id="msg-approval"),
        gateway=_Gateway(),
    )

    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["request_id"].endswith("msg-approval")
    assert outcome["playbook_key"] == "dev_code_update"
    assert outcome["review_status"] == "approval_required"
    assert outcome["failures"] == ["approval_required"]
    assert "risk_judge" in outcome["agent_chain"]
    assert outcome["tools_used"] == []


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_uses_auxiliary_dispatcher_for_ambiguous_request(
    monkeypatch,
) -> None:
    import plugins.governance_os.dispatcher as dispatcher

    calls: list[dict[str, object]] = []

    async def fake_auxiliary_dispatcher(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "playbook_key": "discord_attachment_delivery",
            "confidence": 0.91,
            "reason": "attachment delivery dominates the mixed request",
            "matched_triggers": ["파일 첨부"],
        }

    monkeypatch.setattr(
        dispatcher,
        "_call_auxiliary_dispatcher",
        fake_auxiliary_dispatcher,
        raising=False,
    )

    result = await governance_pre_gateway_dispatch(
        event=_Event("수시 점수 계산 파일 첨부해서 보내줘"),
        gateway=_Gateway(),
    )

    assert calls
    assert calls[0]["task"] == "miho_governance_dispatcher"
    assert result["action"] == "rewrite"
    assert result["intent"] == "discord_attachment_delivery"
    assert result["required_tool"] == "media_delivery_contract"
    assert result["routing_source"] == "miho_governance_dispatcher"


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_uses_auxiliary_router_map_without_keyword_candidate(
    monkeypatch,
) -> None:
    import plugins.governance_os.dispatcher as dispatcher

    registry = load_builtin_registry()
    assert dispatch_request(registry, "방금 내용을 깔끔한 상담 문서로 만들어줘").action == "allow"
    calls: list[dict[str, object]] = []

    async def fake_auxiliary_dispatcher(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "playbook_key": "designed_pdf_artifact",
            "confidence": 0.94,
            "reason": "semantic route map matched new designed document artifact",
            "matched_triggers": [],
            "evidence": ["HTML-first PDF artifact request"],
        }

    monkeypatch.setattr(
        dispatcher,
        "_call_auxiliary_dispatcher",
        fake_auxiliary_dispatcher,
        raising=False,
    )

    result = await governance_pre_gateway_dispatch(
        event=_Event("방금 내용을 깔끔한 상담 문서로 만들어줘"),
        gateway=_Gateway(),
    )

    assert calls
    assert calls[0]["candidates"] == ()
    assert result["action"] == "rewrite"
    assert result["intent"] == "designed_pdf_artifact"
    assert result["required_tool"] == "html_pdf_quality_gate"
    assert result["routing_source"] == "miho_governance_dispatcher"


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_respects_auxiliary_allow_with_playbook_key(
    monkeypatch,
) -> None:
    import plugins.governance_os.dispatcher as dispatcher

    calls: list[dict[str, object]] = []

    async def fake_auxiliary_dispatcher(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "action": "allow",
            "playbook_key": "designed_pdf_artifact",
            "confidence": 0.96,
            "reason": "LLM found no governed request despite a stale playbook field",
            "evidence": ["semantic allow"],
        }

    monkeypatch.setattr(
        dispatcher,
        "_call_auxiliary_dispatcher",
        fake_auxiliary_dispatcher,
        raising=False,
    )

    result = await governance_pre_gateway_dispatch(
        event=_Event("이거 정리해줘"),
        gateway=_Gateway(),
    )

    assert calls
    assert result == {"action": "allow"}


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_sends_thread_context_to_auxiliary_dispatcher(
    monkeypatch,
) -> None:
    import plugins.governance_os.dispatcher as dispatcher

    calls: list[dict[str, object]] = []

    async def fake_auxiliary_dispatcher(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "playbook_key": "designed_pdf_artifact",
            "confidence": 0.94,
            "reason": "reply context asks for a designed PDF artifact",
            "matched_triggers": [],
            "evidence": ["reply_to_text contains the source material"],
        }

    event = _Event("이거 정리해줘")
    event.reply_to_text = "4개월 시즌 운동 프로그램 초안"
    event.channel_context = "최근 대화는 운동 프로그램 상담"
    event.media_urls = ["/tmp/source.md"]
    monkeypatch.setattr(
        dispatcher,
        "_call_auxiliary_dispatcher",
        fake_auxiliary_dispatcher,
        raising=False,
    )

    result = await governance_pre_gateway_dispatch(event=event, gateway=_Gateway())

    assert calls
    context = calls[0]["turn_context"]
    assert isinstance(context, dict)
    assert context["reply_to_text"] == "4개월 시즌 운동 프로그램 초안"
    assert context["channel_context"] == "최근 대화는 운동 프로그램 상담"
    assert context["media"] == [".md"]
    assert result["intent"] == "designed_pdf_artifact"


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_allows_body_agent_when_auxiliary_dispatcher_fails(
    monkeypatch,
) -> None:
    import plugins.governance_os.dispatcher as dispatcher

    async def broken_auxiliary_dispatcher(**_: object) -> dict[str, object]:
        raise RuntimeError("provider offline")

    monkeypatch.setattr(
        dispatcher,
        "_call_auxiliary_dispatcher",
        broken_auxiliary_dispatcher,
        raising=False,
    )

    result = await governance_pre_gateway_dispatch(
        event=_Event("수시 점수 계산 파일 첨부해서 보내줘"),
        gateway=_Gateway(),
    )

    assert result["action"] == "allow"
    assert result["route"] == "governance_os"
    assert result["routing_source"] == "llm_route_unverified"
    assert result["reason"] == "llm_route_unverified"
    assert "text" not in result


@pytest.mark.asyncio
async def test_pre_gateway_dispatch_rejects_auxiliary_playbook_outside_candidates(
    monkeypatch,
) -> None:
    import plugins.governance_os.dispatcher as dispatcher

    async def outside_candidate_dispatcher(**_: object) -> dict[str, object]:
        return {
            "playbook_key": "dev_code_update",
            "confidence": 0.99,
            "reason": "outside candidate should not be trusted",
            "matched_triggers": ["테스트"],
        }

    monkeypatch.setattr(
        dispatcher,
        "_call_auxiliary_dispatcher",
        outside_candidate_dispatcher,
        raising=False,
    )

    result = await governance_pre_gateway_dispatch(
        event=_Event("수시 점수 계산 파일 첨부해서 보내줘"),
        gateway=_Gateway(),
    )

    assert result["action"] == "allow"
    assert result["intent"] != "dev_code_update"
    assert result["routing_source"] == "llm_route_unverified"


@pytest.mark.asyncio
async def test_auxiliary_dispatcher_uses_agent_auxiliary_client(monkeypatch) -> None:
    import agent.auxiliary_client as auxiliary_client
    import plugins.governance_os.dispatcher as dispatcher

    calls: list[dict[str, object]] = []

    async def fake_async_call_llm(**kwargs: object) -> str:
        calls.append(kwargs)
        return json.dumps(
            {
                "playbook_key": "discord_attachment_delivery",
                "confidence": 0.93,
                "reason": "mixed request is delivery-dominant",
                "matched_triggers": ["파일 첨부"],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(auxiliary_client, "async_call_llm", fake_async_call_llm)
    monkeypatch.setattr(auxiliary_client, "extract_content_or_reasoning", lambda value: value)

    registry = load_builtin_registry()
    decision = dispatch_request(registry, "수시 점수 계산 파일 첨부해서 보내줘")
    candidates = dispatcher._score_candidates(
        registry,
        "수시 점수 계산 파일 첨부해서 보내줘".casefold(),
    )

    payload = await dispatcher._call_auxiliary_dispatcher(
        task="miho_governance_dispatcher",
        user_text="수시 점수 계산 파일 첨부해서 보내줘",
        candidate_decision=decision,
        candidates=candidates,
    )

    assert payload["playbook_key"] == "discord_attachment_delivery"
    assert calls
    assert calls[0]["task"] == "miho_governance_dispatcher"
    assert calls[0]["timeout"] == 8
    user_payload = json.loads(calls[0]["messages"][1]["content"])  # type: ignore[index]
    assert user_payload["candidate_scorer"]["playbook_key"]
    assert user_payload["candidates"]
