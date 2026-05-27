"""Tests for LLM-structured academy request routing."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from plugins.academy_ops.natural_router import (
    AcademyNaturalRoute,
    resolve_and_execute_academy_request,
)
import plugins.academy_ops.response_synthesis as response_synthesis
from plugins.academy_ops.response_synthesis import compact_payload
from plugins.academy_ops.thread_context import clear_thread_contexts, remember_thread_context


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


@pytest.fixture(autouse=True)
def _clear_context() -> None:
    clear_thread_contexts()


@pytest.mark.asyncio
async def test_natural_router_uses_llm_json_not_keyword_parsing() -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_resolver(_: list[dict[str, str]]) -> object:
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_schedule_range",
                    "args": {"start_date": "2026-05-01", "end_date": "2026-05-31"},
                    "confidence": 0.96,
                }
            )
        )

    def fake_handler(args: dict, **_: object) -> str:
        calls.append(("academy_schedule_range", args))
        return json.dumps({"ok": True, "message": "5월 학원 일정 2건"}, ensure_ascii=False)

    route = await resolve_and_execute_academy_request(
        "이 문장 내용은 테스트에서 일부러 무시돼야 해",
        resolver=fake_resolver,
        handlers={"academy_schedule_range": fake_handler},
        today="2026-05-26",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [
        (
            "academy_schedule_range",
            {"start_date": "2026-05-01", "end_date": "2026-05-31"},
        )
    ]


@pytest.mark.asyncio
async def test_natural_router_allows_non_academy_requests() -> None:
    async def fake_resolver(_: list[dict[str, str]]) -> object:
        return _Response(json.dumps({"action": "allow", "confidence": 0.2}))

    route = await resolve_and_execute_academy_request(
        "그냥 잡담",
        resolver=fake_resolver,
        handlers={"academy_schedule_range": lambda args, **kwargs: "{}"},
        today="2026-05-26",
    )

    assert route == AcademyNaturalRoute.ALLOW
    assert route.response_text == ""


@pytest.mark.asyncio
async def test_natural_router_timeout_returns_short_response() -> None:
    calls = 0

    async def slow_resolver(_: list[dict[str, str]]) -> object:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return _Response("{}")

    route = await resolve_and_execute_academy_request(
        "5월 학원일정 줘",
        resolver=slow_resolver,
        handlers={"academy_schedule_range": lambda args, **kwargs: "{}"},
        today="2026-05-26",
        resolver_timeout=0.01,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert "학원 서버 응답이 불안정" in route.response_text
    assert calls == 1


@pytest.mark.asyncio
async def test_natural_router_retries_resolver_timeout_before_user_failure() -> None:
    calls = 0

    async def flaky_resolver(_: list[dict[str, str]]) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(0.05)
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_schedule_range",
                    "args": {"start_date": "2026-05-01", "end_date": "2026-05-31"},
                    "confidence": 0.96,
                }
            )
        )

    def handler(args: dict, **_: object) -> str:
        return json.dumps({"ok": True, "message": f"{args['start_date']} 일정 2건"}, ensure_ascii=False)

    route = await resolve_and_execute_academy_request(
        "5월 학원일정 줘",
        resolver=flaky_resolver,
        handlers={"academy_schedule_range": handler},
        today="2026-05-26",
        resolver_timeout=0.01,
        resolver_attempts=2,
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert route.response_text == "2026-05-01 일정 2건"
    assert calls == 2


@pytest.mark.asyncio
async def test_attendance_image_followup_forces_calendar_tool_after_llm_decision() -> None:
    calls: list[tuple[str, dict]] = []
    remember_thread_context(
        "thread-image",
        tool_name="academy_student_attendance_range",
        args={"student_query": "학생A", "start_date": "2026-05-01", "end_date": "2026-05-31"},
        payload={"ok": True, "student": {"name": "학생A"}, "start_date": "2026-05-01", "end_date": "2026-05-31"},
    )

    async def image_resolver(_: list[dict[str, str]]) -> object:
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_student_attendance_range",
                    "args": {"student_query": "", "start_date": "", "end_date": ""},
                    "response_focus": "daily_attendance",
                    "confidence": 0.95,
                }
            )
        )

    def calendar_handler(args: dict, **_: object) -> str:
        calls.append(("calendar", args))
        return json.dumps(
            {
                "ok": True,
                "student": {"name": args["student_query"]},
                "start_date": args["start_date"],
                "end_date": args["end_date"],
                "message": "학생A 출석 달력이야. MEDIA:/tmp/student-a.png",
                "media_tag": "MEDIA:/tmp/student-a.png",
            },
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "날짜별로 정리해서 이미지로줘",
        resolver=image_resolver,
        handlers={
            "academy_student_attendance_range": lambda args, **kwargs: "{}",
            "academy_student_attendance_calendar_image": calendar_handler,
        },
        context_key="thread-image",
        today="2026-05-26",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert "MEDIA:/tmp/student-a.png" in route.response_text
    assert calls == [(
        "calendar",
        {"student_query": "학생A", "start_date": "2026-05-01", "end_date": "2026-05-31", "today": "2026-05-26"},
    )]


@pytest.mark.asyncio
async def test_natural_router_can_route_student_followup_to_context_tool() -> None:
    async def resolver(_: list[dict[str, str]]) -> object:
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_student_context",
                    "args": {"student_query": "서하"},
                    "confidence": 0.95,
                }
            )
        )

    def handler(args: dict, **_: object) -> str:
        return json.dumps(
            {
                "ok": True,
                "operation": "student.context",
                "student": {"name": "이서하"},
                "schedule": [{"weekday": "일", "time_slot_label": "오후반"}],
                "message": "이서하 수업 요일: 일 오후반",
            },
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "서하 나오는 요일이 언제야?",
        resolver=resolver,
        handlers={"academy_student_context": handler},
        today="2026-05-26",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert route.response_text == "이서하 수업 요일: 일 오후반"


@pytest.mark.asyncio
async def test_student_followup_reuses_thread_context_without_name_guessing() -> None:
    calls: list[dict] = []

    async def first_resolver(_: list[dict[str, str]]) -> object:
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_student_attendance_range",
                    "args": {"student_query": "학생A", "start_date": "2026-05-01", "end_date": "2026-05-31"},
                    "confidence": 0.95,
                }
            )
        )

    async def followup_resolver(messages: list[dict[str, str]]) -> object:
        prompt = messages[1]["content"]
        assert '"student_query": "학생A"' in prompt
        assert "학생명을 추측하지 마" in messages[0]["content"]
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_student_attendance_range",
                    "args": {"student_query": "", "start_date": "", "end_date": ""},
                    "confidence": 0.91,
                }
            )
        )

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {
                "ok": True,
                "student": {"name": "학생A"},
                "start_date": args["start_date"],
                "end_date": args["end_date"],
                "summary": {"unchecked": 1},
                "attendance": [{"date": "2026-05-12", "status": "unchecked", "time_slot": "evening"}],
                "message": "학생A 출석 조회",
            },
            ensure_ascii=False,
        )

    await resolve_and_execute_academy_request(
        "학생A 5월 출석 조회",
        resolver=first_resolver,
        handlers={"academy_student_attendance_range": handler},
        context_key="thread-1",
        today="2026-05-26",
        synthesize=False,
    )
    route = await resolve_and_execute_academy_request(
        "미체크 날짜랑 요일만 알려줘",
        resolver=followup_resolver,
        handlers={"academy_student_attendance_range": handler},
        context_key="thread-1",
        today="2026-05-26",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls[1] == {
        "student_query": "학생A",
        "start_date": "2026-05-01",
        "end_date": "2026-05-31",
        "today": "2026-05-26",
    }


@pytest.mark.asyncio
async def test_login_required_request_is_retried_from_thread_context() -> None:
    calls = 0

    async def first_resolver(_: list[dict[str, str]]) -> object:
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_student_attendance_calendar_image",
                    "args": {"student_query": "학생A", "start_date": "2026-05-01", "end_date": "2026-05-31"},
                    "confidence": 0.96,
                }
            )
        )

    async def should_not_resolve(_: list[dict[str, str]]) -> object:
        raise AssertionError("pending request retry should not need another resolver call")

    def handler(args: dict, **_: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return json.dumps({"ok": False, "message": "학원 계정 연결이 만료된 것 같아. `/academy login`으로 다시 연결해줘."}, ensure_ascii=False)
        return json.dumps(
            {
                "ok": True,
                "student": {"name": args["student_query"]},
                "start_date": args["start_date"],
                "end_date": args["end_date"],
                "message": "학생A 출석 달력이야. MEDIA:/tmp/student-a.png",
                "media_tag": "MEDIA:/tmp/student-a.png",
            },
            ensure_ascii=False,
        )

    first = await resolve_and_execute_academy_request(
        "학생A 5월 출석 일자별로 조회해서 이미지 줘",
        resolver=first_resolver,
        handlers={"academy_student_attendance_calendar_image": handler},
        context_key="thread-auth",
        synthesize=False,
    )
    second = await resolve_and_execute_academy_request(
        "로그인 했어",
        resolver=should_not_resolve,
        handlers={"academy_student_attendance_calendar_image": handler},
        context_key="thread-auth",
        synthesize=False,
    )

    assert first == AcademyNaturalRoute.HANDLED
    assert "학원 계정 연결" in first.response_text
    assert second == AcademyNaturalRoute.HANDLED
    assert second.reason == "pending_request_retry"
    assert "MEDIA:/tmp/student-a.png" in second.response_text
    assert calls == 2


def test_compact_payload_keeps_attendance_rows_for_followup_details() -> None:
    payload = {
        "operation": "attendance.student_month",
        "attendance": [{"date": "2026-05-12", "status": "unchecked"}],
    }

    assert compact_payload(payload)["attendance"] == [{"date": "2026-05-12", "status": "unchecked"}]


@pytest.mark.asyncio
async def test_daily_attendance_focus_formats_rows_without_synthesis(monkeypatch) -> None:
    async def resolver(_: list[dict[str, str]]) -> object:
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_student_attendance_range",
                    "args": {"student_query": "학생A", "start_date": "2026-05-01", "end_date": "2026-05-03"},
                    "response_focus": "daily_attendance",
                    "confidence": 0.95,
                }
            )
        )

    def handler(args: dict, **_: object) -> str:
        return json.dumps(
            {
                "ok": True,
                "student": {"name": "학생A"},
                "start_date": args["start_date"],
                "end_date": args["end_date"],
                "attendance": [
                    {"date": "2026-05-01", "status": "absent", "time_slot": "evening", "absence_reason": "사유"},
                    {"date": "2026-05-02", "status": "present", "time_slot": "evening"},
                    {"date": "2026-05-03", "status": "unchecked", "time_slot": "afternoon"},
                ],
                "message": "요약만 있는 기본 메시지",
            },
            ensure_ascii=False,
        )

    async def fail_synthesis(_: str, __: dict) -> str:
        raise AssertionError("daily focus must not call synthesis")

    monkeypatch.setattr(response_synthesis, "synthesize_response", fail_synthesis)

    route = await resolve_and_execute_academy_request(
        "날짜별로 정리해줘",
        resolver=resolver,
        handlers={"academy_student_attendance_range": handler},
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert "학생A 출석 2026-05-01~2026-05-03" in route.response_text
    assert "05/01 금: 결석 / 저녁반 / 사유" in route.response_text
    assert "05/02 토: 출석 / 저녁반" in route.response_text
    assert "05/03 일: 미체크 / 오후반" in route.response_text


@pytest.mark.asyncio
async def test_daily_attendance_focus_labels_future_classes_as_scheduled() -> None:
    async def resolver(_: list[dict[str, str]]) -> object:
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_student_attendance_range",
                    "args": {"student_query": "학생A", "start_date": "2026-05-03", "end_date": "2026-05-04"},
                    "response_focus": "daily_attendance",
                    "confidence": 0.95,
                }
            )
        )

    def handler(args: dict, **_: object) -> str:
        return json.dumps(
            {
                "ok": True,
                "student": {"name": "학생A"},
                "start_date": args["start_date"],
                "end_date": args["end_date"],
                "attendance": [
                    {"date": "2026-05-03", "status": "present", "time_slot": "afternoon"},
                    {"date": "2026-05-04", "status": "upcoming", "time_slot": "evening"},
                ],
                "message": "요약만 있는 기본 메시지",
            },
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "날짜별로 정리해줘",
        resolver=resolver,
        handlers={"academy_student_attendance_range": handler},
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert "05/04 월: 예정 / 저녁반" in route.response_text
    assert "05/04 월: 미체크" not in route.response_text
