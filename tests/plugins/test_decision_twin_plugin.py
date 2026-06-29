"""Tests for the LLM-backed Miho decision-twin pre-dispatch plugin."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.decision_twin import _decision_twin_pre_gateway_dispatch
from plugins.decision_twin.router import annotate_result_text, build_decision_messages, parse_decision_payload
from plugins.decision_twin.router import should_route_decision


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
async def test_decision_twin_hook_payload_contains_context_and_tool_contracts() -> None:
    seen: dict[str, object] = {}

    async def resolver(messages):
        seen.update(json.loads(messages[1]["content"]))
        return {"action": "allow", "confidence": 0.8}

    event = _event("이거 PDF로 정리해줘")
    event.source.thread_id = "thread-42"
    event.reply_to_text = "4개월 시즌 운동 프로그램 초안"
    event.channel_context = "최근 대화는 운동 상담"
    event.media_urls = ["/tmp/source.md"]

    result = await _decision_twin_pre_gateway_dispatch(
        event=event,
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
        owner_context_builder=lambda _text: "새 PDF 제작은 html_pdf_quality_gate를 탄다.",
    )

    assert result == {"action": "allow"}
    assert seen["user_text"] == "이거 PDF로 정리해줘"
    assert seen["owner_memory"] == "새 PDF 제작은 html_pdf_quality_gate를 탄다."
    assert "html_pdf_quality_gate" in seen["tool_contracts"]
    turn_context = seen["turn_context"]
    assert isinstance(turn_context, dict)
    assert turn_context["thread_id"] == "thread-42"
    assert turn_context["reply_to_text"] == "4개월 시즌 운동 프로그램 초안"
    assert turn_context["channel_context"] == "최근 대화는 운동 상담"
    assert turn_context["media"] == [".md"]


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
    # 라우팅은 참고 힌트가 아니라 실행 지시로 붙는다
    assert "라우팅 지시" in result["text"]
    assert "필수 실행 도구: life_record_summary" in result["text"]
    assert "MUST use required_tool before final answer" in result["text"]
    assert "현재 스레드 생기부 DB를 요약한다" in result["text"]
    assert "참고용" not in result["text"]


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


@pytest.mark.asyncio
async def test_decision_twin_hook_rejects_unknown_required_tool() -> None:
    async def resolver(_messages):
        return {
            "action": "route",
            "required_tool": "made_up_unregistered_tool",
            "confidence": 0.99,
        }

    result = await _decision_twin_pre_gateway_dispatch(
        event=_event("이거 전용 도구로 해줘"),
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
    assert "현재 상태" in joined
    assert "session_search" in joined


def test_annotate_result_text_preserves_user_text() -> None:
    """원문이 맨 앞에 보존되고, routing directive가 뒤에 붙는다."""
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
    # 라우팅은 실행 지시다
    assert "라우팅 지시" in text
    assert "필수 실행 도구" in text
    assert "MUST use required_tool before final answer" in text
    assert "국민대 경희대 인하대 3개 리포트를 만든다" in text
    assert "academy_hakjong_report_package" in text
    assert "참고용" not in text


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

    assert "필수 실행 도구:" not in text
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
    # 필수 도구 지시로 포함
    assert "jungsi_student_university_score" in text
    assert "MUST use required_tool before final answer" in text
    # 잘못된 fallback 문구 없다
    assert "로그인 링크로 대체하지 마라" not in text


def test_should_route_decision_rejects_unknown_required_tool() -> None:
    decision = parse_decision_payload(
        {
            "action": "route",
            "route": "academy_ops",
            "required_tool": "made_up_unregistered_tool",
            "intent": "존재하지 않는 도구 호출",
            "confidence": 0.99,
        }
    )

    assert should_route_decision(decision) is False


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
async def test_decision_twin_does_not_swallow_recommendation_correction_with_region_gate() -> None:
    async def resolver(_messages):
        return {
            "action": "route",
            "intent": "기존 후보표에서 조건전형/성별 오류 수정",
            "confidence": 0.86,
            "needs_region_question": True,
            "evidence": ["LLM이 지역 누락으로 오판했지만 본문은 기존 후보표 수정이다"],
        }

    event = _event("아 지역균형 중 단대 체교는 예외로 세팅하고 교과전형은 추천하지말아 그리고 남자인데 여자가 나오잖아 그것다 수정해줘")
    event.channel_context = "직전 답변: 동혁이 수도권·강원·충청권 후보 명단"

    result = await _decision_twin_pre_gateway_dispatch(
        event=event,
        gateway=SimpleNamespace(_is_user_authorized=lambda _source: True),
        resolver=resolver,
    )

    assert result == {"action": "allow"}


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
