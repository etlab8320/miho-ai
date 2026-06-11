"""Tests for daily academy attendance roster image routing."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import plugins.academy_ops.natural_router as natural_router
from plugins.academy_ops.academy_query_tools import _attendance_day_tool_handler
from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from tests.plugins.academy_router_helpers import router_execute
from tests.plugins.test_academy_student_card import FakeAcademyClient


class FakeDayRosterRenderer:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.payloads: list[dict] = []

    def render(self, payload: dict) -> Path:
        self.payloads.append(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"png")
        return self.path


def _payload(raw: str) -> dict:
    return json.loads(raw)


def test_attendance_day_tool_can_return_roster_image_media(tmp_path: Path) -> None:
    renderer = FakeDayRosterRenderer(tmp_path / "attendance-day.png")

    result = _payload(
        _attendance_day_tool_handler(
            {"date": "2026-05-25", "image": True},
            client=FakeAcademyClient(),
            renderer=renderer,
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "attendance.day"
    assert result["image_path"] == str(tmp_path / "attendance-day.png")
    assert result["media_tag"] == f"MEDIA:{tmp_path / 'attendance-day.png'}"
    assert "MEDIA:" in result["message"]
    assert renderer.payloads[0]["date"] == "2026-05-25"


def test_attendance_day_image_contract_is_visible_to_llm_router() -> None:
    prompt = "\n".join(
        message["content"]
        for message in natural_router._resolver_messages(
            "오늘 출석해야할 학생들 명단좀 이미지로 줘",
            "2026-05-29",
        )
    )

    contract = natural_router.TOOL_CONTRACTS["academy_attendance_day"]
    assert "image" in contract["args"]
    assert "학생 전체" in contract["purpose"]
    assert "명단" in prompt
    assert "image=true" in prompt


@pytest.mark.asyncio
async def test_attendance_day_image_request_no_keyword_injection_on_semantic_abstain(monkeypatch) -> None:
    """semantic이 abstain(None)하면 keyword 폴백 없이 image 주입이 일어나지 않는다."""
    from plugins.academy_ops import route_overrides

    route_overrides._last_output.update(text=None, label=None, hit=False)
    monkeypatch.setattr(
        "plugins.academy_ops.route_overrides.semantic_intents.classify",
        lambda text, group, intents, **kwargs: None,
    )

    calls: list[dict] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        content = router_execute("academy_attendance_day", {"date": "2026-05-29"}, confidence=0.96)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps({"ok": True, "message": "출석 명단"}, ensure_ascii=False)

    route = await resolve_and_execute_academy_request(
        "오늘 출석해야할 학생들 명단좀 이미지로 줘",
        resolver=fake_resolver,
        handlers={"academy_attendance_day": handler},
        today="2026-05-29",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    # semantic abstain → image 주입 없음
    assert calls == [{"date": "2026-05-29"}]
    route_overrides._last_output.update(text=None, label=None, hit=False)


@pytest.mark.asyncio
async def test_attendance_day_image_request_sets_image_arg_when_semantic_returns_image(monkeypatch) -> None:
    """semantic이 image를 반환하면 image=True 주입이 일어난다."""
    from plugins.academy_ops import route_overrides

    route_overrides._last_output.update(text=None, label=None, hit=False)
    monkeypatch.setattr(
        "plugins.academy_ops.route_overrides.semantic_intents.classify",
        lambda text, group, intents, **kwargs: "image",
    )

    calls: list[dict] = []

    async def fake_resolver(messages: list[dict[str, str]]) -> object:
        content = router_execute("academy_attendance_day", {"date": "2026-05-29"}, confidence=0.96)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps({"ok": True, "message": "출석 명단 이미지야. MEDIA:/tmp/day.png"}, ensure_ascii=False)

    route = await resolve_and_execute_academy_request(
        "오늘 출석해야할 학생들 명단좀 이미지로 줘",
        resolver=fake_resolver,
        handlers={"academy_attendance_day": handler},
        today="2026-05-29",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [{"date": "2026-05-29", "image": True}]
    assert "MEDIA:" in route.response_text
    route_overrides._last_output.update(text=None, label=None, hit=False)
