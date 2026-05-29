"""Routing tests for Peak student performance record lookups."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from tests.plugins.academy_router_helpers import router_execute


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


@pytest.mark.asyncio
async def test_student_performance_record_routes_to_record_lookup_not_attendance_or_plan() -> None:
    calls: list[dict] = []

    async def resolver(messages: list[dict[str, str]]) -> object:
        prompt = "\n".join(message["content"] for message in messages)
        assert "academy_student_record_lookup" in prompt
        assert "학생 수행 기록" in prompt
        assert "어제 여민석 제자리멀리뛰기 기록좀줘" in prompt
        return _Response(
            router_execute(
                "academy_student_record_lookup",
                {
                    "student_query": "여민석",
                    "event_query": "제자리멀리뛰기",
                    "date": "2026-05-28",
                    "today": "2026-05-29",
                },
                intent="student performance record lookup",
                evidence=["student name, event name, and relative date"],
                confidence=0.96,
            )
        )

    def record_handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {
                "ok": True,
                "operation": "student.record_lookup",
                "student": {"name": "여민석"},
                "records": [{"event_name": "제자리멀리뛰기", "measured_at": "2026-05-28", "value": 248, "unit": "cm"}],
                "message": "여민석 2026-05-28 제자리멀리뛰기 기록\n- 2026-05-28: 제자리멀리뛰기 248cm",
            },
            ensure_ascii=False,
        )

    def wrong_handler(args: dict, **_: object) -> str:
        raise AssertionError(f"wrong academy tool called: {args!r}")

    route = await resolve_and_execute_academy_request(
        "어제 여민석 제자리멀리뛰기 기록좀줘",
        resolver=resolver,
        handlers={
            "academy_student_record_lookup": record_handler,
            "academy_student_attendance_range": wrong_handler,
            "academy_plan_by_date": wrong_handler,
        },
        today="2026-05-29",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [
        {
            "student_query": "여민석",
            "event_query": "제자리멀리뛰기",
            "date": "2026-05-28",
            "today": "2026-05-29",
        }
    ]
    assert "제자리멀리뛰기 248cm" in route.response_text
