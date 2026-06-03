"""Follow-up handling for Peak class assignment counts."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from plugins.academy_ops.thread_context import clear_thread_contexts
from tests.plugins.academy_router_helpers import router_execute


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


@pytest.fixture(autouse=True)
def _clear_contexts():
    clear_thread_contexts()
    yield
    clear_thread_contexts()


@pytest.mark.asyncio
async def test_assignment_followup_adds_counts_from_previous_assignment_context() -> None:
    async def first_resolver(messages: list[dict[str, str]]) -> object:
        return _Response(router_execute("academy_assignment_by_date", {"date": "2026-06-03", "time_slot": ""}))

    async def followup_resolver(messages: list[dict[str, str]]) -> object:
        raise AssertionError("assignment count follow-up should not call the LLM router")

    def handler(args: dict, **_: object) -> str:
        return json.dumps(_assignment_payload(), ensure_ascii=False)

    first = await resolve_and_execute_academy_request(
        "오늘 수업 배정 알려줘",
        resolver=first_resolver,
        handlers={"academy_assignment_by_date": handler},
        context_key="assignment-thread",
        today="2026-06-03",
        synthesize=False,
    )
    followup = await resolve_and_execute_academy_request(
        "맨뒤에 몇명씩인지 보여줘",
        resolver=followup_resolver,
        handlers={"academy_assignment_by_date": handler},
        context_key="assignment-thread",
        today="2026-06-03",
        synthesize=False,
    )

    assert first == AcademyNaturalRoute.HANDLED
    assert followup == AcademyNaturalRoute.HANDLED
    assert followup.reason == "assignment_count_followup"
    assert "1반 / 오철민 (2명): 백지민, 이지유" in followup.response_text
    assert "2반 / 정의솔 (1명): 박지안" in followup.response_text
    assert "미배정 (2명): 조윤태, 홍예지" in followup.response_text


@pytest.mark.asyncio
async def test_assignment_followup_handles_explicit_per_class_count_wording() -> None:
    async def first_resolver(messages: list[dict[str, str]]) -> object:
        return _Response(router_execute("academy_assignment_by_date", {"date": "2026-06-03", "time_slot": ""}))

    async def followup_resolver(messages: list[dict[str, str]]) -> object:
        raise AssertionError("explicit assignment count follow-up should be handled from context")

    def handler(args: dict, **_: object) -> str:
        return json.dumps(_assignment_payload(), ensure_ascii=False)

    await resolve_and_execute_academy_request(
        "오늘 반배치 알려줘",
        resolver=first_resolver,
        handlers={"academy_assignment_by_date": handler},
        context_key="assignment-thread",
        today="2026-06-03",
        synthesize=False,
    )
    followup = await resolve_and_execute_academy_request(
        "아니 반배치 각 인원표시해서 달라고",
        resolver=followup_resolver,
        handlers={"academy_assignment_by_date": handler},
        context_key="assignment-thread",
        today="2026-06-03",
        synthesize=False,
    )

    assert followup == AcademyNaturalRoute.HANDLED
    assert "2026-06-03 반배치 각 반 인원" in followup.response_text
    assert "저녁반" in followup.response_text
    assert "1반 / 오철민 (2명)" in followup.response_text


def _assignment_payload() -> dict:
    return {
        "ok": True,
        "operation": "assignment.by_date",
        "date": "2026-06-03",
        "time_slot": "",
        "summary": {"classes": 2, "assigned_students": 3, "waiting_students": 2},
        "slots": {
            "evening": {
                "classes": [
                    {
                        "class_num": 1,
                        "instructors": [{"name": "오철민"}],
                        "students": [{"student_name": "백지민"}, {"student_name": "이지유"}],
                    },
                    {
                        "class_num": 2,
                        "instructors": [{"name": "정의솔"}],
                        "students": [{"student_name": "박지안"}],
                    },
                ],
                "waiting_students": [{"student_name": "조윤태"}, {"student_name": "홍예지"}],
            }
        },
        "message": "2026-06-03 반배치: 2개 반, 배정 3명, 미배정 2명",
    }
