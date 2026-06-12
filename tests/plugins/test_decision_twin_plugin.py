"""Tests for the LLM-backed Miho decision-twin pre-dispatch plugin."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.decision_twin import _decision_twin_pre_gateway_dispatch
from plugins.decision_twin.contracts import decision_tool_contracts
from plugins.decision_twin.router import annotate_result_text, build_decision_messages, parse_decision_payload


def _event(text: str, *, user_id: str = "u1") -> MessageEvent:
    return MessageEvent(
        text=text,
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id=user_id,
            chat_id="channel-1",
            guild_id="guild-1",
        ),
    )


@pytest.mark.asyncio
async def test_decision_twin_rewrites_to_required_tool_from_llm_judge() -> None:
    async def resolver(_messages):
        return {
            "action": "route",
            "route": "life_record",
            "intent": "life_record.summary",
            "required_tool": "life_record_summary",
            "confidence": 0.92,
            "evidence": ["사용자가 현재 스레드 생기부 요약을 요청했다"],
            "tool_instruction": "현재 스레드 생기부 DB를 요약한다",
        }

    user_text = "가은이 생기부 핵심만 다시 정리해줘"
    result = await _decision_twin_pre_gateway_dispatch(
        event=_event(user_text),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
        owner_context_builder=lambda _text: "생기부는 반드시 life_record_* 도구로 조회한다.",
    )

    assert result["action"] == "rewrite"
    assert result["route"] == "decision_twin"
    assert result["intent"] == "life_record.summary"
    assert result["required_tool"] == "life_record_summary"
    assert result["confidence"] == 0.92
    # 원문 보존: rewrite된 text에 사용자 원문 전체가 포함된다
    assert user_text in result["text"]
    # 힌트 헤더가 참고용으로 붙는다
    assert "라우팅 힌트" in result["text"]
    assert "참고용" in result["text"]
    # 강제 문구가 없다
    assert "반드시" not in result["text"]
    assert "도구 지시:" not in result["text"]


@pytest.mark.asyncio
async def test_decision_twin_rewrites_hakjong_report_without_guard_side_effect() -> None:
    """_mark_required_tool_route 제거 후 rewrite는 정상 작동한다."""

    async def resolver(_messages):
        return {
            "action": "route",
            "route": "academy_ops",
            "intent": "hakjong.report.package",
            "required_tool": "academy_hakjong_report_package",
            "confidence": 0.94,
            "evidence": ["학생부종합전형 상담용 리포트 PDF/HTML 패키지를 요청했다"],
            "tool_instruction": "프리미엄 학종 리포트 패키지 계약을 사용한다",
        }

    user_text = "가은 학생 4개 대학 학종 상담 리포트 파일로 보내줘"
    result = await _decision_twin_pre_gateway_dispatch(
        event=_event(user_text),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
    )

    assert result["action"] == "rewrite"
    assert result["required_tool"] == "academy_hakjong_report_package"
    # 원문 보존
    assert user_text in result["text"]


@pytest.mark.asyncio
async def test_decision_twin_skips_when_sender_is_not_authorized() -> None:
    calls = 0

    async def resolver(_messages):
        nonlocal calls
        calls += 1
        return {"action": "route", "required_tool": "life_record_summary", "confidence": 1}

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("생기부 봐줘", user_id="intruder"),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: False),
        resolver=resolver,
    )

    assert result == {"action": "allow"}
    assert calls == 0


@pytest.mark.asyncio
async def test_decision_twin_allows_low_confidence_or_malformed_payload() -> None:
    async def resolver(_messages):
        return {"action": "route", "required_tool": "life_record_summary", "confidence": 0.41}

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("이거 해줘"),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
    )

    assert result == {"action": "allow"}


def test_decision_prompt_contains_context_and_tool_contracts() -> None:
    messages = build_decision_messages(
        user_text="학종 리포트 파일 보내줘",
        owner_context="학종 리포트는 검증 도구 통과 후 MEDIA로 전달한다.",
        turn_context={"media": [".pdf"], "reply_to_text": "직전 산출물"},
    )
    joined = "\n".join(message["content"] for message in messages)

    assert "JSON만 반환" in joined
    assert "owner_memory" in joined
    assert "tool_contracts" in joined
    assert "academy_hakjong_report_package" in joined
    assert "life_record_summary" in joined
    assert "키워드 하나" in joined


def test_annotate_result_text_preserves_user_text() -> None:
    """원문이 맨 앞에 보존되고, 힌트는 참고용으로 뒤에 붙는다."""
    decision = parse_decision_payload(
        {
            "action": "route",
            "route": "academy_ops",
            "required_tool": "academy_hakjong_report_package",
            "intent": "학종 리포트 PDF 생성",
            "confidence": 0.94,
            "evidence": ["학종 리포트 요청"],
            "tool_instruction": "국민대 경희대 인하대 3개 리포트를 만든다",
        }
    )

    user_text = "가은이 3개 학교 학종 리포트로 줘"
    text = annotate_result_text(user_text, decision)

    # 원문이 맨 앞에 있다
    assert text.startswith(user_text)
    # 힌트는 참고용이다
    assert "라우팅 힌트" in text
    assert "참고용" in text
    assert "최종 판단과 도구 선택은 네가 직접 한다" in text
    # 추천 도구 포함
    assert "academy_hakjong_report_package" in text
    # 강제 문구 없다
    assert "반드시" not in text
    assert "경로가 잠겨 있지 않다" not in text


def test_annotate_result_text_omits_recommended_tool_line_when_empty() -> None:
    """required_tool 없으면 추천 도구 줄이 생략된다."""
    decision = parse_decision_payload(
        {
            "action": "route",
            "intent": "일반 대화",
            "confidence": 0.8,
            "evidence": ["근거"],
        }
    )

    text = annotate_result_text("안녕", decision)

    assert "추천 도구:" not in text
    assert "안녕" in text


def test_annotate_result_text_media_delivery_no_login_fallbacks() -> None:
    decision = parse_decision_payload(
        {
            "action": "route",
            "route": "gateway_media",
            "required_tool": "media_delivery_contract",
            "intent": "직전 파일을 첨부로 다시 전달",
            "confidence": 0.9,
            "tool_instruction": "직전 리포트 PDF를 MEDIA 태그로 다시 전달한다",
        }
    )

    user_text = "아니 파일을 줘야지 첨부해서"
    text = annotate_result_text(user_text, decision)

    # 원문 보존
    assert user_text in text
    # 강제 contract 문구 없다
    assert "MEDIA:<absolute_path>" not in text
    assert "로그인 링크" not in text


def test_annotate_result_text_score_tool_hint_only() -> None:
    decision = parse_decision_payload(
        {
            "action": "route",
            "route": "jungsi",
            "required_tool": "jungsi_student_university_score",
            "intent": "대학별 환산점수 계산",
            "confidence": 0.9,
            "tool_instruction": "백석대 순천향대 관동대 환산점수를 계산한다",
        }
    )

    user_text = "백석대 순천향대 관동대 꺼 로 내신환산점수 계산해줘봐"
    text = annotate_result_text(user_text, decision)

    # 원문 보존
    assert user_text in text
    # 추천 도구 힌트로 포함
    assert "jungsi_student_university_score" in text
    # 강제 contract 문구 없다
    assert "로그인 링크로 대체하지 마라" not in text


@pytest.mark.asyncio
async def test_decision_twin_allows_jungsi_login_for_hakjong_context_without_guard() -> None:
    """domain_guard 제거 후 clarify/route 결정은 LLM 판단에 맡긴다. rewrite 통과."""

    async def resolver(_messages):
        return {
            "action": "route",
            "route": "jungsi",
            "intent": "hakjong.report.login",
            "required_tool": "jungsi_login",
            "confidence": 0.98,
            "evidence": ["학종 리포트 요청을 로그인 문제로 오판했다"],
            "tool_instruction": "정시엔진 로그인 링크를 발급한다",
        }

    user_text = "말이 좀 긴데 결국 학종 리포트 파일을 제대로 보내달라는 거야"
    result = await _decision_twin_pre_gateway_dispatch(
        event=_event(user_text),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
        owner_context_builder=lambda _text: "학종 리포트는 생기부/수시 근거와 premium_hakjong_report 계약을 사용한다.",
    )

    # 가드 없음 — LLM이 route 결정하면 rewrite로 통과. 원문은 보존된다.
    assert result["action"] == "rewrite"
    assert user_text in result["text"]


@pytest.mark.asyncio
async def test_decision_twin_allows_score_tool_for_susi_score_context() -> None:
    async def resolver(_messages):
        return {
            "action": "route",
            "route": "jungsi",
            "intent": "학생 점수로 대학별 환산점수와 전년도 컷을 비교",
            "required_tool": "jungsi_student_university_score",
            "confidence": 0.9,
            "evidence": ["환산점수와 작년 합격자 점수를 요청했다"],
            "tool_instruction": "학생 점수와 대학별 반영식으로 환산점수/컷을 계산한다",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("종환이 점수로 내신환산이랑 작년 합격자 점수 보고 6개만 상향 중립 안전으로 뽑아줘"),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
        owner_context_builder=lambda _text: "수시 실기/교과 추천은 학생 환산점수와 전년도 컷을 대조해야 한다.",
    )

    assert result["action"] == "rewrite"
    assert result["required_tool"] == "jungsi_student_university_score"


@pytest.mark.asyncio
async def test_decision_twin_allows_score_tool_with_life_record_thread_memory() -> None:
    async def resolver(_messages):
        return {
            "action": "route",
            "route": "jungsi",
            "intent": "수시 점수 추천 후보의 환산점수 검증",
            "required_tool": "jungsi_student_university_score",
            "confidence": 0.9,
            "evidence": ["환산점수가 맞는지 물었다"],
            "tool_instruction": "학생 점수와 대학 반영식으로 환산점수를 검증한다",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("강원대 강릉캠퍼스 점수 환산점수 저거 맞아? 꽤 높게 나오네?"),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
        owner_context_builder=lambda _text: (
            "이 스레드는 생기부와 학종 상담 이력이 있지만, "
            "수시 점수 추천은 학생 환산점수와 전년도 컷을 대조해야 한다."
        ),
    )

    assert result["action"] == "rewrite"
    assert result["required_tool"] == "jungsi_student_university_score"


@pytest.mark.asyncio
async def test_decision_twin_clarify_returns_allow() -> None:
    """clarify 결정은 무조건 allow로 처리된다."""

    async def resolver(_messages):
        return {
            "action": "clarify",
            "intent": "종환 학생의 유리한 체대 실기전형 6개 학교 확인",
            "confidence": 0.91,
            "user_message": "체대 실기전형을 말하는 걸까?",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event(
            "종환이 생기부 성적보고, 서울경기인천 충청권, 대전, 강원 권에서 "
            "가장유리한학교들을 선별해서, 6개 상향 2개 할만한곳 4개 추려서 "
            "종환시 내신환산점수랑 해서 리스트줘"
        ),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
        owner_context_builder=lambda _text: "수시 실기/교과 추천은 학생 환산점수와 전년도 컷을 대조해야 한다.",
    )

    assert result == {"action": "allow"}


@pytest.mark.asyncio
async def test_decision_twin_clarify_returns_allow_regardless_of_confidence() -> None:
    """clarify는 confidence와 무관하게 allow다."""

    async def resolver(_messages):
        return {
            "action": "clarify",
            "intent": "학생 성적 분석 대상 확인",
            "confidence": 0.88,
            "user_message": "어느 학생 기준으로 볼지 알려줘.",
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("내신환산점수 봐줘"),
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
    )

    assert result == {"action": "allow"}


def test_parse_decision_payload_accepts_json_string() -> None:
    decision = parse_decision_payload(
        '{"action":"route","route":"academy_ops","required_tool":"academy_student_card_image",'
        '"intent":"academy.student_card","confidence":0.88,"evidence":["학생 카드 요청"]}'
    )

    assert decision.action == "route"
    assert decision.route == "academy_ops"
    assert decision.required_tool == "academy_student_card_image"
    assert decision.confidence == 0.88
    assert decision.evidence == ("학생 카드 요청",)


def test_decision_contracts_cover_every_registered_tool() -> None:
    from miho_cli.plugins import discover_plugins
    from tools.registry import discover_builtin_tools, registry

    discover_builtin_tools()
    discover_plugins(force=True)

    contracts = decision_tool_contracts()
    registered_tools = set(registry.get_all_tool_names())
    missing = sorted(registered_tools - set(contracts))

    assert missing == []
    assert contracts["send_message"]["domain"] == "messaging"
    assert contracts["terminal"]["domain"] == "terminal"
    assert contracts["academy_student_card_image"]["domain"] == "academy_ops"


def test_core_domain_contracts_are_not_generic_fallbacks() -> None:
    contracts = decision_tool_contracts()
    core_tools = (
        "life_record_ingest_pdf",
        "life_record_summary",
        "life_record_lookup",
        "academy_hakjong_report_package",
        "academy_render_image",
        "academy_report_image",
        "send_message",
        "jungsi_login",
    )

    for tool_name in core_tools:
        contract = contracts[tool_name]
        purpose = contract["purpose"]
        assert len(purpose) >= 35
        assert not purpose.startswith("Registered Miho tool")
        assert contract["domain"]


def test_domain_guard_module_absent() -> None:
    """domain_guard.py가 삭제됐으므로 import가 실패해야 한다."""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("plugins.decision_twin.domain_guard")


@pytest.mark.asyncio
async def test_region_gate_asks_before_recommendation(monkeypatch):
    """추천 라우팅인데 지역 미언급이면 현관에서 지역 질문을 직접 보낸다."""
    from plugins.decision_twin import _decision_twin_pre_gateway_dispatch

    async def resolver(messages):
        return {
            "action": "route",
            "required_tool": "susi27_recommend_candidates",
            "intent": "실기전형 추천",
            "confidence": 0.95,
            "region_in_text": False,
        }

    event = SimpleNamespace(text="종환이 실기전형 6개 추천해줘", source=object(), media_urls=[],
                            reply_to_text="", channel_context="", channel_prompt="")
    gateway = SimpleNamespace(_is_user_authorized=lambda s: True)
    result = await _decision_twin_pre_gateway_dispatch(
        event=event, gateway=gateway, resolver=resolver, owner_context_builder=lambda t: "")
    assert result["action"] == "respond"
    assert result["reason"] == "region_gate"
    assert "지역" in result["text"]


@pytest.mark.asyncio
async def test_region_gate_passes_when_region_mentioned(monkeypatch):
    from plugins.decision_twin import _decision_twin_pre_gateway_dispatch

    async def resolver(messages):
        return {
            "action": "route",
            "required_tool": "susi27_recommend_candidates",
            "intent": "실기전형 추천",
            "confidence": 0.95,
            "region_in_text": True,
        }

    event = SimpleNamespace(text="종환이 실기전형 강원·경기로 추천해줘", source=object(), media_urls=[],
                            reply_to_text="", channel_context="", channel_prompt="")
    gateway = SimpleNamespace(_is_user_authorized=lambda s: True)
    result = await _decision_twin_pre_gateway_dispatch(
        event=event, gateway=gateway, resolver=resolver, owner_context_builder=lambda t: "")
    assert result["action"] == "rewrite"
