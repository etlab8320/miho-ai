"""Tests for high-confidence academy preflight routes."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import plugins.academy_ops.natural_router as natural_router
from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


@pytest.mark.asyncio
async def test_routes_trial_lesson_schedule_without_llm() -> None:
    calls: list[dict] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        raise AssertionError(f"resolver should not run for unambiguous trial query: {messages!r}")

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
async def test_routes_explicit_student_month_attendance_without_llm() -> None:
    calls: list[dict] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        raise AssertionError(f"resolver should not run for explicit attendance query: {messages!r}")

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
async def test_routes_colloquial_student_attendance_suffix_without_llm() -> None:
    calls: list[dict] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        raise AssertionError(f"resolver should not run for explicit attendance query: {messages!r}")

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
async def test_routes_explicit_student_attendance_image_without_llm() -> None:
    calls: list[dict] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        raise AssertionError(f"resolver should not run for explicit attendance image query: {messages!r}")

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


def test_trial_lesson_contract_is_visible_to_llm_router() -> None:
    prompt = "\n".join(
        message["content"]
        for message in natural_router._resolver_messages(
            "이번주 체험수업 학생있어?",
            "2026-05-27",
        )
    )

    assert "trial_only" in prompt


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
    assert calls[0]["extra_body"] == {}
