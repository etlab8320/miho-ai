"""Routing tests for Peak student performance record lookups."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from plugins.academy_ops.route_arg_normalization import normalize_route_args, normalize_route_decision_tools
from tests.plugins.academy_router_helpers import router_execute


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


def test_student_record_route_args_recover_recent_when_router_uses_today_only() -> None:
    args = normalize_route_args(
        "academy_student_record_lookup",
        {
            "student_query": "김동혁",
            "event_query": "",
            "date": "2026-06-03",
            "today": "2026-06-03",
            "period_days": 1,
        },
        today="2026-06-03",
    )

    assert args["period_days"] == 30
    assert args["fallback_recent_when_empty"] is True


def test_student_record_chart_conversion_keeps_attempt_limit_not_tiny_date_window() -> None:
    decision = normalize_route_decision_tools(
        "학생 최근 5회차 실기 그래프 이미지로 줘",
        {
            "actions": [
                {
                    "tool": "academy_student_record_lookup",
                    "args": {
                        "student_query": "김동혁",
                        "event_query": "",
                        "date": "2026-06-03",
                        "today": "2026-06-03",
                        "period_days": 5,
                    },
                }
            ]
        },
    )

    action = decision["actions"][0]
    assert action["tool"] == "academy_student_record_chart_image"
    assert action["args"] == {
        "student_query": "김동혁",
        "event_query": "",
        "today": "2026-06-03",
        "period_days": 180,
        "limit": 5,
    }


def test_student_record_chart_args_reject_zero_day_window() -> None:
    args = normalize_route_args(
        "academy_student_record_chart_image",
        {
            "student_query": "깅동혁",
            "event_query": "",
            "today": "2026-06-03",
            "period_days": 0,
            "limit": 5,
        },
    )

    assert args == {
        "student_query": "깅동혁",
        "event_query": "",
        "today": "2026-06-03",
        "period_days": 180,
        "limit": 5,
    }


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


@pytest.mark.asyncio
async def test_student_record_fast_path_handles_router_model_failure(monkeypatch) -> None:
    calls: list[dict] = []

    def classify(text: str, group_key: str, *_: object, **__: object) -> str | None:
        if group_key == "academy_student_record_fast_path":
            return "record"
        if group_key == "academy_output_format":
            return "none"
        return None

    monkeypatch.setattr("plugins.academy_ops.student_record_fast_path.semantic_intents.classify", classify)

    async def failing_resolver(_: list[dict[str, str]]) -> object:
        raise RuntimeError("router model unavailable")

    def record_handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {
                "ok": True,
                "operation": "student.record_lookup",
                "student": {"name": "김동혁"},
                "records": [{"event_name": "제자리멀리뛰기", "measured_at": "2026-05-30", "value": 250, "unit": "cm"}],
                "message": "김동혁 최근 실기 기록\n- 2026-05-30: 제자리멀리뛰기 250cm",
            },
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "김동혁 최근실기기록 보여줘",
        resolver=failing_resolver,
        handlers={"academy_student_record_lookup": record_handler},
        today="2026-06-03",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert route.reason == "student_record_fast_path"
    assert calls == [
        {
            "student_query": "김동혁 최근실기기록 보여줘",
            "event_query": "",
            "date": "",
            "today": "2026-06-03",
            "period_days": 30,
        }
    ]
    assert "제자리멀리뛰기 250cm" in route.response_text


@pytest.mark.asyncio
async def test_student_record_fast_path_abstains_for_image_requests(monkeypatch) -> None:
    def classify(text: str, group_key: str, *_: object, **__: object) -> str | None:
        if group_key == "academy_student_record_fast_path":
            return "record"
        if group_key == "academy_output_format":
            return "image"
        return None

    monkeypatch.setattr("plugins.academy_ops.student_record_fast_path.semantic_intents.classify", classify)

    async def resolver(_: list[dict[str, str]]) -> object:
        return _Response(json.dumps({"action": "allow", "domain": "academy_ops", "confidence": 0.2}))

    def record_handler(args: dict, **_: object) -> str:
        raise AssertionError(f"image request should not use text fast path: {args!r}")

    route = await resolve_and_execute_academy_request(
        "김동혁 종목별 최근기록 추세 이미지 부탁해",
        resolver=resolver,
        handlers={"academy_student_record_lookup": record_handler},
        today="2026-06-03",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.ALLOW


@pytest.mark.asyncio
async def test_student_record_chart_fast_path_handles_image_requests(monkeypatch) -> None:
    calls: list[dict] = []

    def classify(text: str, group_key: str, *_: object, **__: object) -> str | None:
        if group_key == "academy_student_record_chart_fast_path":
            return "chart"
        if group_key == "academy_student_record_fast_path":
            return "record"
        if group_key == "academy_output_format":
            return "image"
        return None

    monkeypatch.setattr("plugins.academy_ops.student_record_fast_path.semantic_intents.classify", classify)

    async def failing_resolver(_: list[dict[str, str]]) -> object:
        raise RuntimeError("router model should not be needed")

    def chart_handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {
                "ok": True,
                "operation": "student.record_chart_image",
                "student": {"name": "김동혁"},
                "message": "김동혁 최근 5회차 실기 그래프야. MEDIA:/tmp/chart.png",
                "media_tag": "MEDIA:/tmp/chart.png",
            },
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "깅동혁 최근 5회차실기기록들 각 종목별 그래프로 그려서 이미지로줘",
        resolver=failing_resolver,
        handlers={"academy_student_record_chart_image": chart_handler},
        today="2026-06-03",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert route.reason == "student_record_chart_fast_path"
    assert calls == [
        {
            "student_query": "깅동혁 최근 5회차실기기록들 각 종목별 그래프로 그려서 이미지로줘",
            "event_query": "",
            "today": "2026-06-03",
            "period_days": 180,
            "limit": 5,
        }
    ]
    assert "MEDIA:/tmp/chart.png" in route.response_text
