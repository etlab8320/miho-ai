"""Replay production-like academy gateway failures from real logs."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import plugins.academy_ops.assignment_followup as assignment_followup
from gateway.generated_media import append_missing_generated_media_directives
from gateway.platforms.base import BasePlatformAdapter
from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from plugins.academy_ops.thread_context import clear_thread_contexts
from tests.plugins.academy_router_helpers import router_execute


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "miho_pipeline_log_replay.json"


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


@pytest.fixture(autouse=True)
def _clear_contexts():
    clear_thread_contexts()
    yield
    clear_thread_contexts()


def _cases(kind: str) -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [case for case in payload["cases"] if case["kind"] == kind]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _cases("assignment_followup_count"), ids=lambda case: case["name"])
async def test_log_replay_assignment_count_followup_uses_thread_context(case: dict[str, Any]) -> None:
    await _prime_assignment_context()

    async def resolver(messages: list[dict[str, str]]) -> object:
        raise AssertionError("assignment count follow-up should not call the LLM router")

    route = await resolve_and_execute_academy_request(
        case["utterance"],
        resolver=resolver,
        handlers={"academy_assignment_by_date": _assignment_handler},
        context_key="log-replay-assignment",
        today="2026-06-03",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert route.reason == case["expected_reason"]
    assert "1반 / 오철민 (2명)" in route.response_text
    assert "미배정 (2명)" in route.response_text


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _cases("assignment_followup_image"), ids=lambda case: case["name"])
async def test_log_replay_assignment_image_followup_sends_one_media(
    case: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _prime_assignment_context()

    def fake_render(args: dict[str, Any], **_: object) -> str:
        return _media_tool_payload("/tmp/assignment-log-replay.png")

    monkeypatch.setattr(assignment_followup, "_render_image_tool_handler", fake_render)

    async def resolver(messages: list[dict[str, str]]) -> object:
        raise AssertionError("assignment image follow-up should not call the LLM router")

    route = await resolve_and_execute_academy_request(
        case["utterance"],
        resolver=resolver,
        handlers={"academy_assignment_by_date": _assignment_handler},
        context_key="log-replay-assignment",
        today="2026-06-03",
        synthesize=False,
    )
    media, cleaned = BasePlatformAdapter.extract_media(route.response_text)

    assert route == AcademyNaturalRoute.HANDLED
    assert route.reason == case["expected_reason"]
    assert len(media) == case["expected_media_count"]
    assert "MEDIA:" not in cleaned


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _cases("academy_router_execute"), ids=lambda case: case["name"])
async def test_log_replay_student_chart_requests_hit_chart_tool_once(case: dict[str, Any]) -> None:
    calls: list[dict[str, Any]] = []

    async def resolver(messages: list[dict[str, str]]) -> object:
        prompt = "\n".join(message["content"] for message in messages)
        assert case["utterance"] in prompt
        assert case["expected_tool"] in prompt
        return _Response(router_execute(case["expected_tool"], {"student_query": "김동혁", "limit": 5}))

    def chart_handler(args: dict[str, Any], **_: object) -> str:
        calls.append(args)
        return _media_tool_payload("/tmp/student-chart-log-replay.png")

    route = await resolve_and_execute_academy_request(
        case["utterance"],
        resolver=resolver,
        handlers={case["expected_tool"]: chart_handler},
        context_key=f"log-replay-{case['name']}",
        today="2026-06-03",
        synthesize=False,
    )
    media, cleaned = BasePlatformAdapter.extract_media(route.response_text)

    assert route == AcademyNaturalRoute.HANDLED
    assert len(calls) == 1
    assert calls[0]["limit"] == 5
    assert len(media) == case["expected_media_count"]
    assert "MEDIA:" not in cleaned


@pytest.mark.parametrize("case", _cases("generated_media_dedupe"), ids=lambda case: case["name"])
def test_log_replay_structured_media_promoter_keeps_one_attachment(
    case: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import gateway.generated_media as generated_media

    image = tmp_path / ".miho" / "media_cache" / "academy_reports" / f"{case['name']}.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    promoted_dir = tmp_path / ".miho" / "cache" / "media" / "gateway_promoted"
    monkeypatch.setattr(generated_media, "_MEDIA_CACHE_DIR", promoted_dir)
    tool_output = _media_tool_payload(str(image))
    final_response = f"정리했어.\nMEDIA:{image}"

    promoted = append_missing_generated_media_directives(
        final_response,
        [
            {"role": "user", "content": case["utterance"]},
            {"role": "tool", "tool_name": "academy_report_image", "content": tool_output},
        ],
    )
    media, cleaned = BasePlatformAdapter.extract_media(promoted)

    assert len(media) == case["expected_media_count"]
    assert "MEDIA:" not in cleaned
    assert not (promoted_dir / image.name).exists()


async def _prime_assignment_context() -> None:
    async def resolver(messages: list[dict[str, str]]) -> object:
        return _Response(router_execute("academy_assignment_by_date", {"date": "2026-06-03"}))

    route = await resolve_and_execute_academy_request(
        "오늘 수업 배정 알려줘",
        resolver=resolver,
        handlers={"academy_assignment_by_date": _assignment_handler},
        context_key="log-replay-assignment",
        today="2026-06-03",
        synthesize=False,
    )
    assert route == AcademyNaturalRoute.HANDLED


def _assignment_handler(args: dict[str, Any], **_: object) -> str:
    return json.dumps(
        {
            "ok": True,
            "operation": "assignment.by_date",
            "date": "2026-06-03",
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
        },
        ensure_ascii=False,
    )


def _media_tool_payload(path: str) -> str:
    return json.dumps(
        {
            "ok": True,
            "message": f"이미지야. MEDIA:{path}",
            "image_path": path,
            "media_tag": f"MEDIA:{path}",
        },
        ensure_ascii=False,
    )
