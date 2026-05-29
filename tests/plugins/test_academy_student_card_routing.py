"""Regression tests for student-card natural routing."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from plugins.academy_ops.natural_router import (
    AcademyNaturalRoute,
    TOOL_CONTRACTS,
    resolve_and_execute_academy_request,
)
from plugins.academy_ops.thread_context import clear_thread_contexts, remember_thread_context
from tests.plugins.academy_router_helpers import router_execute


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


@pytest.fixture(autouse=True)
def _clear_context() -> None:
    clear_thread_contexts()


def test_student_card_contract_excludes_summary_for_card_image_requests() -> None:
    assert "카드/이미지/파일 전달 요청에는 쓰지 않음" in TOOL_CONTRACTS["academy_student_summary"]["purpose"]
    assert "학생관리카드" in TOOL_CONTRACTS["academy_student_card_image"]["purpose"]


def test_consultation_candidate_contract_supports_png_image_requests() -> None:
    assert "PNG 이미지" in TOOL_CONTRACTS["academy_consultation_candidates"]["purpose"]


@pytest.mark.asyncio
async def test_student_management_card_request_forces_card_image_when_resolver_picks_summary() -> None:
    calls: list[dict] = []

    async def resolver(_: list[dict[str, str]]) -> object:
        return _Response(router_execute("academy_student_summary", {"student_query": "백지민"}, confidence=0.93))

    def card_handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {
                "ok": True,
                "card": {"profile": {"name": "백지민"}},
                "message": "백지민 학생 카드야. MEDIA:/tmp/baek-card.png",
                "media_tag": "MEDIA:/tmp/baek-card.png",
            },
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "백지민 학생관리카드 줘",
        resolver=resolver,
        handlers={
            "academy_student_summary": lambda args, **kwargs: "{}",
            "academy_student_card_image": card_handler,
        },
        context_key="thread-card",
        today="2026-05-29",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [{"student_query": "백지민", "today": "2026-05-29"}]
    assert "MEDIA:/tmp/baek-card.png" in route.response_text


@pytest.mark.asyncio
async def test_card_image_followup_reuses_student_card_context_not_previous_attendance() -> None:
    calls: list[dict] = []
    remember_thread_context(
        "thread-card-followup",
        tool_name="academy_student_card_image",
        args={"student_query": "백지민", "today": "2026-05-29"},
        payload={"ok": True, "card": {"profile": {"name": "백지민"}}, "message": "백지민 학생 카드야."},
    )

    async def resolver(_: list[dict[str, str]]) -> object:
        return _Response(router_execute("academy_student_summary", {"student_query": ""}, confidence=0.9))

    def card_handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {
                "ok": True,
                "card": {"profile": {"name": args["student_query"]}},
                "message": "백지민 학생 카드야. MEDIA:/tmp/baek-card-v2.png",
                "media_tag": "MEDIA:/tmp/baek-card-v2.png",
            },
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "이미지를 줘야지",
        resolver=resolver,
        handlers={
            "academy_student_summary": lambda args, **kwargs: "{}",
            "academy_student_card_image": card_handler,
            "academy_student_attendance_calendar_image": lambda args, **kwargs: "{}",
        },
        context_key="thread-card-followup",
        today="2026-05-29",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [{"student_query": "백지민", "today": "2026-05-29"}]
    assert "baek-card-v2.png" in route.response_text
