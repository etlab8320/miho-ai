"""Route metadata coverage for academy natural routing."""

from __future__ import annotations

import json

import pytest

from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from tests.plugins.academy_router_helpers import router_execute


class _Response:
    def __init__(self, content: str):
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


@pytest.mark.asyncio
async def test_natural_router_records_executed_tool_as_reason() -> None:
    async def fake_resolver(_: list[dict[str, str]]) -> object:
        return _Response(router_execute("academy_schedule_range", {"start_date": "2026-05-01"}))

    def fake_handler(args: dict, **_: object) -> str:
        return json.dumps({"ok": True, "message": "5월 일정"}, ensure_ascii=False)

    route = await resolve_and_execute_academy_request(
        "5월 일정 알려줘",
        resolver=fake_resolver,
        handlers={"academy_schedule_range": fake_handler},
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert route.reason == "academy_schedule_range"
