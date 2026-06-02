"""Productization baseline for academy semantic routing quality."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from types import SimpleNamespace
from typing import Any

import pytest

import plugins.academy_ops.natural_router as natural_router
from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from tests.plugins.academy_router_helpers import router_allow, router_execute


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


@dataclass(frozen=True)
class RoutingScenario:
    name: str
    utterance: str
    expected_tool: str
    expected_args: dict[str, Any]
    wrong_tools: tuple[str, ...] = field(default_factory=tuple)
    response_focus: str = ""


BASELINE_SCENARIOS = (
    RoutingScenario(
        name="future roster",
        utterance="다음주 금요일 수업 나와야 하는 애들 명단 줘",
        expected_tool="academy_class_roster_range",
        expected_args={
            "start_date": "2026-06-12",
            "end_date": "2026-06-12",
            "with_roster": True,
        },
        wrong_tools=("academy_attendance_day", "academy_student_attendance_range"),
    ),
    RoutingScenario(
        name="actual attendance image",
        utterance="어제 실제 출결 체크된거 이미지로 보여줘",
        expected_tool="academy_attendance_day",
        expected_args={"date": "2026-06-02", "image": True},
        wrong_tools=("academy_class_roster_range", "academy_student_attendance_calendar_image"),
    ),
    RoutingScenario(
        name="student record typo",
        utterance="김보민 제멀 기록좀 봐줘",
        expected_tool="academy_student_record_lookup",
        expected_args={
            "student_query": "김보민",
            "event_query": "제멀",
            "date": "",
            "today": "2026-06-03",
        },
        wrong_tools=("academy_student_attendance_range", "academy_plan_by_date"),
    ),
    RoutingScenario(
        name="monthly aggregate",
        utterance="5월 월말테스트 남녀 평균 학교 빼고 정리해줘",
        expected_tool="academy_monthly_test_records",
        expected_args={
            "event_query": "",
            "test_id": None,
            "test_month": "2026-05",
            "exclude_schools": True,
            "today": "2026-06-03",
        },
        wrong_tools=("academy_student_record_lookup", "academy_schedule_range"),
    ),
)


def test_router_prompt_defines_speed_as_correct_first_tool_choice() -> None:
    messages = natural_router._resolver_messages(
        "오늘 출석 봐줘",
        "2026-06-03",
        temporal_context="now: 2026-06-03T10:00:00+09:00",
    )

    system_prompt = messages[0]["content"]
    assert "정확한 도구와 인자를 첫 선택" in system_prompt
    assert "잘못된 도구를 골라 실패한 뒤 재시도" in system_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", BASELINE_SCENARIOS, ids=[s.name for s in BASELINE_SCENARIOS])
async def test_product_baseline_uses_correct_tool_on_first_execution(scenario: RoutingScenario) -> None:
    resolver_calls = 0
    handler_calls: list[tuple[str, dict[str, Any]]] = []

    async def resolver(messages: list[dict[str, str]]) -> object:
        nonlocal resolver_calls
        resolver_calls += 1
        prompt = "\n".join(message["content"] for message in messages)
        assert scenario.utterance in prompt
        assert scenario.expected_tool in prompt
        return _Response(
            router_execute(
                scenario.expected_tool,
                scenario.expected_args,
                confidence=0.96,
                response_focus=scenario.response_focus,
            )
        )

    def expected_handler(args: dict[str, Any], **_: object) -> str:
        handler_calls.append((scenario.expected_tool, args))
        return json.dumps({"ok": True, "message": f"{scenario.name} handled"}, ensure_ascii=False)

    def wrong_handler(args: dict[str, Any], **_: object) -> str:
        raise AssertionError(f"wrong academy tool called with {args!r}")

    handlers = {scenario.expected_tool: expected_handler}
    handlers.update({tool: wrong_handler for tool in scenario.wrong_tools})
    route = await resolve_and_execute_academy_request(
        scenario.utterance,
        resolver=resolver,
        handlers=handlers,
        today="2026-06-03",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert resolver_calls == 1
    assert handler_calls == [(scenario.expected_tool, scenario.expected_args)]


@pytest.mark.asyncio
async def test_product_baseline_keeps_non_academy_request_out_of_tools() -> None:
    handler_called = False

    async def resolver(messages: list[dict[str, str]]) -> object:
        assert "오늘 비오나?" in messages[-1]["content"]
        return _Response(router_allow())

    def handler(args: dict[str, Any], **_: object) -> str:
        nonlocal handler_called
        handler_called = True
        return json.dumps({"ok": True, "message": str(args)}, ensure_ascii=False)

    route = await resolve_and_execute_academy_request(
        "오늘 비오나?",
        resolver=resolver,
        handlers={"academy_schedule_range": handler},
        today="2026-06-03",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.ALLOW
    assert route.reason == "not_academy"
    assert handler_called is False
