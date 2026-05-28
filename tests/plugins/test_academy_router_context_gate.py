"""Context-gate coverage for academy LLM routing."""

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
async def test_diet_log_with_work_phrase_is_allowed_by_llm_context() -> None:
    async def resolver(messages: list[dict[str, str]]) -> object:
        prompt = "\n".join(message["content"] for message in messages)
        assert "키워드 하나가 아니라 전체 문맥" in prompt
        assert "324칼로리 쿠팡 도시락" in prompt
        return _Response(
            json.dumps(
                {
                    "action": "allow",
                    "domain": "non_academy",
                    "intent": "dated diet correction",
                    "evidence": ["meal details and calorie correction"],
                    "ambiguous": False,
                    "confidence": 0.94,
                },
                ensure_ascii=False,
            )
        )

    def handler(args: dict, **_: object) -> str:
        raise AssertionError(f"academy staff tool must not run: {args!r}")

    route = await resolve_and_execute_academy_request(
        "너 지금 어제 먹은거랑 섞어서 말햇어! 오늘은 바나나 1개 먹고, "
        "출근해서 324칼로리 쿠팡 도시락 먹엇고, 닭가슴살 한덩이 먹엇어",
        resolver=resolver,
        handlers={"academy_staff_attendance_day": handler},
        today="2026-05-28",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.ALLOW
    assert route.reason == "not_academy"


@pytest.mark.asyncio
async def test_execute_without_academy_domain_evidence_is_rejected() -> None:
    async def resolver(_: list[dict[str, str]]) -> object:
        return _Response(
            json.dumps(
                {
                    "action": "execute",
                    "tool": "academy_staff_attendance_day",
                    "args": {"date": "2026-05-28"},
                    "confidence": 0.99,
                }
            )
        )

    route = await resolve_and_execute_academy_request(
        "오늘 먹은 거 날짜별로 정리해줘",
        resolver=resolver,
        handlers={"academy_staff_attendance_day": lambda args, **kwargs: "{}"},
        today="2026-05-28",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.ALLOW
    assert route.reason == "domain_not_academy"


@pytest.mark.asyncio
async def test_explicit_staff_attendance_request_still_executes() -> None:
    calls: list[dict] = []

    async def resolver(_: list[dict[str, str]]) -> object:
        return _Response(
            router_execute(
                "academy_staff_attendance_day",
                {"date": "2026-05-28"},
                intent="staff attendance lookup",
                evidence=["user asks which academy instructors worked"],
            )
        )

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps({"ok": True, "message": "2026-05-28 출근 강사: 안예준"}, ensure_ascii=False)

    route = await resolve_and_execute_academy_request(
        "오늘 출근한 강사 누구야?",
        resolver=resolver,
        handlers={"academy_staff_attendance_day": handler},
        today="2026-05-28",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [{"date": "2026-05-28"}]
