"""Tests for LLM-proposed multi-tool academy route plans."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from tests.plugins.academy_router_helpers import router_execute_plan


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


@pytest.mark.asyncio
async def test_routes_staff_schedule_and_roster_plan_without_body_agent() -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        assert "오늘 출근일정과 학생들 반배치 보여줘" in messages[-1]["content"]
        return _Response(
            router_execute_plan(
                [
                    {
                        "title": "출근일정",
                        "tool": "academy_staff_schedule_day",
                        "args": {"date": "2026-06-03", "time_slot": "", "include_owner": False},
                        "intent": "오늘 출근 예정 강사 조회",
                        "evidence": ["출근일정 조회 요청"],
                    },
                    {
                        "title": "학생 반배치",
                        "tool": "academy_assignment_by_date",
                        "args": {"date": "2026-06-03", "time_slot": ""},
                        "intent": "오늘 수업 배정 학생 조회",
                        "evidence": ["학생 반배치 조회 요청"],
                    },
                ]
            )
        )

    def staff_handler(args: dict, **_: object) -> str:
        calls.append(("academy_staff_schedule_day", args))
        return json.dumps({"ok": True, "message": "2026-06-03 출근 예정 강사\n저녁반: 오철민, 정의솔"}, ensure_ascii=False)

    def assignment_handler(args: dict, **_: object) -> str:
        calls.append(("academy_assignment_by_date", args))
        return json.dumps(
            {
                "ok": True,
                "message": "2026-06-03 반배치: 4개 반, 배정 38명, 미배정 1명\n"
                "저녁반\n- 1반 / 오철민: 백지민, 김유준",
            },
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "오늘 출근일정과 학생들 반배치 보여줘",
        resolver=fake_resolver,
        handlers={
            "academy_staff_schedule_day": staff_handler,
            "academy_assignment_by_date": assignment_handler,
        },
        today="2026-06-03",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert route.reason == "route_plan"
    assert calls == [
        ("academy_staff_schedule_day", {"date": "2026-06-03", "time_slot": "", "include_owner": False}),
        ("academy_assignment_by_date", {"date": "2026-06-03", "time_slot": ""}),
    ]
    assert "출근일정" in route.response_text
    assert "학생 반배치" in route.response_text
    assert "반배치: 4개 반" in route.response_text
    assert "저녁반: 오철민, 정의솔" in route.response_text
    assert "1반 / 오철민" in route.response_text
