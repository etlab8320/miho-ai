"""Tests for semantic academy natural routes."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import plugins.academy_ops.natural_router as natural_router
from plugins.academy_ops.commentary_config import ROUTER_MODEL
from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from plugins.academy_ops.route_preflight import academy_preflight_decision


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


@pytest.mark.asyncio
async def test_routes_trial_lesson_schedule_through_router() -> None:
    calls: list[dict] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        assert "오늘 체험수업 학생있어?" in messages[-1]["content"]
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_consultation_schedule_range",
                    "args": {
                        "start_date": "2026-05-27",
                        "end_date": "2026-05-27",
                        "new_registration_only": False,
                        "trial_only": True,
                    },
                    "confidence": 0.95,
                },
                ensure_ascii=False,
            )
        )

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {"ok": True, "message": "2026-05-27 체험수업 일정 1건\n- 18:00: 이체험 고2 체험고"},
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "오늘 체험수업 학생있어?",
        resolver=fake_resolver,
        handlers={"academy_consultation_schedule_range": handler},
        today="2026-05-27",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [
        {
            "start_date": "2026-05-27",
            "end_date": "2026-05-27",
            "new_registration_only": False,
            "trial_only": True,
        }
    ]
    assert "이체험" in route.response_text


@pytest.mark.asyncio
async def test_routes_explicit_student_month_attendance_through_router() -> None:
    calls: list[dict] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        assert "백지민 5월 출석조회좀" in messages[-1]["content"]
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_student_attendance_range",
                    "args": {
                        "student_query": "백지민",
                        "start_date": "2026-05-01",
                        "end_date": "2026-05-31",
                        "today": "2026-05-27",
                    },
                    "response_focus": "summary",
                    "confidence": 0.96,
                },
                ensure_ascii=False,
            )
        )

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {"ok": True, "message": "백지민 출석 조회 2026-05-01~2026-05-31: 출석 10회"},
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "백지민 5월 출석조회좀",
        resolver=fake_resolver,
        handlers={"academy_student_attendance_range": handler},
        today="2026-05-27",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [
        {
            "student_query": "백지민",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "today": "2026-05-27",
        }
    ]
    assert "출석 10회" in route.response_text


@pytest.mark.asyncio
async def test_routes_colloquial_student_attendance_suffix_through_router() -> None:
    calls: list[dict] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        assert "백지민 5월 출석 조회좀해봐" in messages[-1]["content"]
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_student_attendance_range",
                    "args": {
                        "student_query": "백지민",
                        "start_date": "2026-05-01",
                        "end_date": "2026-05-31",
                        "today": "2026-05-27",
                    },
                    "confidence": 0.96,
                },
                ensure_ascii=False,
            )
        )

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps({"ok": True, "message": "백지민 5월 출석"}, ensure_ascii=False)

    route = await resolve_and_execute_academy_request(
        "백지민 5월 출석 조회좀해봐",
        resolver=fake_resolver,
        handlers={"academy_student_attendance_range": handler},
        today="2026-05-27",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls[0]["student_query"] == "백지민"
    assert calls[0]["start_date"] == "2026-05-01"
    assert calls[0]["end_date"] == "2026-05-31"


@pytest.mark.asyncio
async def test_routes_explicit_student_attendance_image_through_router() -> None:
    calls: list[dict] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        assert "백지민 5월 출석조회 이미지로 줘" in messages[-1]["content"]
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_student_attendance_calendar_image",
                    "args": {
                        "student_query": "백지민",
                        "start_date": "2026-05-01",
                        "end_date": "2026-05-31",
                        "today": "2026-05-27",
                    },
                    "confidence": 0.97,
                },
                ensure_ascii=False,
            )
        )

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {
                "ok": True,
                "message": "백지민 출석 달력이야. MEDIA:/tmp/attendance.png",
                "media_tag": "MEDIA:/tmp/attendance.png",
            },
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "백지민 5월 출석조회 이미지로 줘",
        resolver=fake_resolver,
        handlers={"academy_student_attendance_calendar_image": handler},
        today="2026-05-27",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls[0]["student_query"] == "백지민"
    assert calls[0]["start_date"] == "2026-05-01"
    assert calls[0]["end_date"] == "2026-05-31"
    assert "MEDIA:" in route.response_text


@pytest.mark.asyncio
async def test_routes_staff_month_count_through_router() -> None:
    calls: list[dict] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        assert "정의솔 강사 5월 총 몇번 출근했어?" in messages[-1]["content"]
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_staff_attendance_range",
                    "args": {
                        "staff_query": "정의솔",
                        "start_date": "2026-05-01",
                        "end_date": "2026-05-31",
                    },
                    "confidence": 0.96,
                },
                ensure_ascii=False,
            )
        )

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {"ok": True, "message": "정의솔 2026-05-01~2026-05-31 출근 4회."},
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "정의솔 강사 5월 총 몇번 출근했어?",
        resolver=fake_resolver,
        handlers={"academy_staff_attendance_range": handler},
        today="2026-05-27",
        synthesize=True,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [
        {
            "staff_query": "정의솔",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
        }
    ]
    assert route.response_text == "정의솔 2026-05-01~2026-05-31 출근 4회."


@pytest.mark.asyncio
async def test_routes_staff_followup_month_count_from_thread_context_through_router() -> None:
    calls: list[dict] = []
    decisions = [
        {
            "action": "execute",
            "tool": "academy_staff_attendance_range",
            "args": {
                "staff_query": "김세희",
                "start_date": "2026-05-18",
                "end_date": "2026-05-24",
            },
            "confidence": 0.96,
        },
        {
            "action": "execute",
            "tool": "academy_staff_attendance_range",
            "args": {
                "staff_query": "",
                "start_date": "2026-05-01",
                "end_date": "2026-05-31",
            },
            "confidence": 0.96,
        },
    ]

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        assert "도구 계약" in messages[-1]["content"]
        return _Response(json.dumps(decisions.pop(0), ensure_ascii=False))

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {
                "ok": True,
                "staff_query": args["staff_query"],
                "start_date": args["start_date"],
                "end_date": args["end_date"],
                "summary": {"worked": 1},
                "instructors": [{"name": args["staff_query"], "worked": 1}],
                "message": f"{args['staff_query']} 출근 1회",
            },
            ensure_ascii=False,
        )

    first = await resolve_and_execute_academy_request(
        "김세희 강사 저번주 출근일정좀 줘",
        resolver=fake_resolver,
        handlers={"academy_staff_attendance_range": handler},
        context_key="staff-thread",
        today="2026-05-27",
        synthesize=True,
    )
    followup = await resolve_and_execute_academy_request(
        "그럼 5월 총 몇번 출근했어?",
        resolver=fake_resolver,
        handlers={"academy_staff_attendance_range": handler},
        context_key="staff-thread",
        today="2026-05-27",
        synthesize=True,
    )

    assert first == AcademyNaturalRoute.HANDLED
    assert followup == AcademyNaturalRoute.HANDLED
    assert calls[0] == {
        "staff_query": "김세희",
        "start_date": "2026-05-18",
        "end_date": "2026-05-24",
    }
    assert calls[1] == {
        "staff_query": "김세희",
        "start_date": "2026-05-01",
        "end_date": "2026-05-31",
    }


def test_preflight_ignores_casual_tomorrow_work_phrase() -> None:
    decision = academy_preflight_decision(
        "일단 지금 75프로까지 내려갔으니까 내일 출근해서 보면 되겠지~",
        today="2026-05-28",
    )

    assert decision is None


def test_preflight_defers_staff_attendance_advice_question_to_router() -> None:
    decision = academy_preflight_decision(
        "오늘 출근한 강사가 너무 적은데, 다음에 더 추가해야할까?",
        today="2026-05-28",
    )

    assert decision is None


@pytest.mark.asyncio
async def test_casual_tomorrow_work_phrase_does_not_execute_staff_attendance() -> None:
    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        assert "내일 출근해서" in messages[-1]["content"]
        return _Response(json.dumps({"action": "allow", "confidence": 0.1}))

    def handler(args: dict, **_: object) -> str:
        raise AssertionError(f"staff attendance tool should not run for casual phrasing: {args!r}")

    route = await resolve_and_execute_academy_request(
        "일단 지금 75프로까지 내려갔으니까 내일 출근해서 보면 되겠지~",
        resolver=fake_resolver,
        handlers={"academy_staff_attendance_day": handler},
        today="2026-05-28",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.ALLOW


@pytest.mark.asyncio
async def test_staff_attendance_advice_question_does_not_execute_preflight() -> None:
    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        assert "출근한 강사가 너무 적은데" in messages[-1]["content"]
        return _Response(json.dumps({"action": "allow", "confidence": 0.1}))

    def handler(args: dict, **_: object) -> str:
        raise AssertionError(f"staff attendance tool should not run for advice question: {args!r}")

    route = await resolve_and_execute_academy_request(
        "오늘 출근한 강사가 너무 적은데, 다음에 더 추가해야할까?",
        resolver=fake_resolver,
        handlers={"academy_staff_attendance_day": handler},
        today="2026-05-28",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.ALLOW


def test_preflight_defers_explicit_staff_day_lookup_to_router() -> None:
    decision = academy_preflight_decision(
        "어제 누구 출근했는지 알려줘",
        today="2026-05-28",
    )

    assert decision is None


def test_preflight_defers_explicit_staff_day_count_lookup_to_router() -> None:
    decision = academy_preflight_decision(
        "오늘 출근한 강사 몇 명이야?",
        today="2026-05-28",
    )

    assert decision is None


def test_trial_lesson_contract_is_visible_to_llm_router() -> None:
    prompt = "\n".join(
        message["content"]
        for message in natural_router._resolver_messages(
            "이번주 체험수업 학생있어?",
            "2026-05-27",
        )
    )

    assert "trial_only" in prompt


def test_staff_attendance_false_positive_guard_is_visible_to_llm_router() -> None:
    prompt = "\n".join(
        message["content"]
        for message in natural_router._resolver_messages(
            "내일 출근해서 보면 되겠지",
            "2026-05-28",
        )
    )

    assert "출근해서" in prompt
    assert "일상 표현" in prompt
    assert "action=allow" in prompt


def test_staff_advice_guard_is_visible_to_llm_router() -> None:
    prompt = "\n".join(
        message["content"]
        for message in natural_router._resolver_messages(
            "오늘 출근한 강사가 너무 적은데, 다음에 더 추가해야할까?",
            "2026-05-28",
        )
    )

    assert "단어만으로 도구를 실행하지 마" in prompt
    assert "더 추가해야 할까" in prompt
    assert "action=allow" in prompt


@pytest.mark.asyncio
async def test_default_router_resolver_omits_reasoning_extra_body(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_call_llm(**kwargs):
        calls.append(kwargs)
        return _Response(json.dumps({"action": "allow", "confidence": 0.1}))

    monkeypatch.setattr("agent.auxiliary_client.async_call_llm", fake_call_llm)

    await natural_router.default_resolver([{"role": "user", "content": "오늘 체험수업 학생있어?"}])

    assert calls
    assert calls[0]["task"] == "academy_request_router"
    assert calls[0]["model"] == ROUTER_MODEL
    assert calls[0]["extra_body"] == {}
