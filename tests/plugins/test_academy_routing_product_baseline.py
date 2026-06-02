"""Productization baseline for academy semantic routing quality."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
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
    expected_action: str
    expected_tool: str
    expected_args: dict[str, Any]
    wrong_tools: tuple[str, ...] = field(default_factory=tuple)
    response_focus: str = ""


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "academy_routing_product_baseline.json"


def _load_scenarios() -> tuple[RoutingScenario, ...]:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return tuple(
        RoutingScenario(
            name=str(item["name"]),
            utterance=str(item["utterance"]),
            expected_action=str(item["expected_action"]),
            expected_tool=str(item.get("expected_tool") or ""),
            expected_args=dict(item.get("expected_args") or {}),
            wrong_tools=tuple(item.get("wrong_tools") or ()),
            response_focus=str(item.get("response_focus") or ""),
        )
        for item in raw["scenarios"]
    )


BASELINE_SCENARIOS = _load_scenarios()
EXECUTE_SCENARIOS = tuple(s for s in BASELINE_SCENARIOS if s.expected_action == "execute")
ALLOW_SCENARIOS = tuple(s for s in BASELINE_SCENARIOS if s.expected_action == "allow")


def test_router_prompt_defines_speed_as_correct_first_tool_choice() -> None:
    messages = natural_router._resolver_messages(
        "오늘 출석 봐줘",
        "2026-06-03",
        temporal_context="now: 2026-06-03T10:00:00+09:00",
    )

    system_prompt = messages[0]["content"]
    assert "정확한 도구와 인자를 첫 선택" in system_prompt
    assert "잘못된 도구를 골라 실패한 뒤 재시도" in system_prompt


def test_product_baseline_fixture_has_initial_500_cases() -> None:
    assert len(BASELINE_SCENARIOS) == 500
    assert len(EXECUTE_SCENARIOS) >= 470
    assert len(ALLOW_SCENARIOS) >= 20


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", EXECUTE_SCENARIOS, ids=[s.name for s in EXECUTE_SCENARIOS])
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
@pytest.mark.parametrize("scenario", ALLOW_SCENARIOS, ids=[s.name for s in ALLOW_SCENARIOS])
async def test_product_baseline_keeps_non_academy_request_out_of_tools(scenario: RoutingScenario) -> None:
    handler_called = False

    async def resolver(messages: list[dict[str, str]]) -> object:
        assert scenario.utterance in messages[-1]["content"]
        return _Response(router_allow())

    def handler(args: dict[str, Any], **_: object) -> str:
        nonlocal handler_called
        handler_called = True
        return json.dumps({"ok": True, "message": str(args)}, ensure_ascii=False)

    route = await resolve_and_execute_academy_request(
        scenario.utterance,
        resolver=resolver,
        handlers={"academy_schedule_range": handler},
        today="2026-06-03",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.ALLOW
    assert route.reason == "not_academy"
    assert handler_called is False
