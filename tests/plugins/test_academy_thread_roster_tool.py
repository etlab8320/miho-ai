"""Tests for thread-stored academy roster lookup."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from plugins.academy_ops.context import capture_gateway_context
from plugins.academy_ops.natural_router import (
    AcademyNaturalRoute,
    _resolver_messages,
    resolve_and_execute_academy_request,
)
from plugins.academy_ops.thread_roster_tool import (
    _thread_roster_lookup_tool_handler,
    parse_markdown_rosters,
)
from tests.plugins.academy_router_helpers import router_execute


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


@pytest.fixture()
def discord_thread_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    source = SimpleNamespace(
        platform=SimpleNamespace(value="discord"),
        guild_id="guild-1",
        parent_chat_id="channel-1",
        chat_id="thread-1",
        thread_id="thread-1",
        chat_name="정시반편성",
        chat_topic="",
        user_id="user-1",
    )
    event = SimpleNamespace(source=source, text="")
    capture_gateway_context(event)
    return tmp_path


def test_parse_markdown_rosters_is_generic() -> None:
    rosters = parse_markdown_rosters(
        "# 2027 정시반 편성표\n\n"
        "## A대반\n\n"
        "- 학생1\n"
        "- 학생2\n\n"
        "## B대반\n\n"
        "- 학생2\n"
        "- 학생3\n"
    )

    assert rosters == {"A대반": ["학생1", "학생2"], "B대반": ["학생2", "학생3"]}


def test_parse_markdown_rosters_supports_inline_assignment_lines() -> None:
    rosters = parse_markdown_rosters(
        "# 2027 정시반 편성표\n\n"
        "국민대반: 박세영, 최혜은\n"
        "숭실대반 - 박세영, 최재원, 윤지언\n"
    )

    assert rosters == {
        "국민대반": ["박세영", "최혜은"],
        "숭실대반": ["박세영", "최재원", "윤지언"],
    }


def test_router_prompt_exposes_thread_roster_tool_contract() -> None:
    messages = _resolver_messages(
        "스레드에 저장해둔 반 명단 줘",
        "2026-06-26",
        {"kind": "generic"},
    )

    assert "academy_thread_roster_lookup" in messages[1]["content"]
    assert "스레드 작업파일" in messages[0]["content"]
    assert "학원 DB 조회나 날짜별 수업 예정 명단이 아니다" in messages[0]["content"]


def test_thread_roster_lookup_reads_current_discord_thread_work_file(discord_thread_workspace) -> None:
    work_dir = (
        discord_thread_workspace
        / "discord/guilds/guild-1/channels/channel-1__channel-1/"
        "threads/thread-1__thread-1/work"
    )
    work_dir.mkdir(parents=True)
    (work_dir / "jungsi_class_assignments.md").write_text(
        "# 2027 정시반 편성표\n\n"
        "## 국민대반\n\n"
        "- 박세영\n"
        "- 최혜은\n\n"
        "## 숭실대반\n\n"
        "- 박세영\n"
        "- 최재원\n"
        "- 윤지언\n",
        encoding="utf-8",
    )

    result = json.loads(
        _thread_roster_lookup_tool_handler({"roster_names": ["국민대반", "숭실대반"]})
    )

    assert result["ok"] is True
    assert result["rosters"] == {
        "국민대반": ["박세영", "최혜은"],
        "숭실대반": ["박세영", "최재원", "윤지언"],
    }
    assert result["duplicates"] == {"박세영": ["국민대반", "숭실대반"]}
    assert "국민대반" in result["message"]
    assert "학원 DB" not in result["message"]


def test_thread_roster_lookup_reads_inline_assignment_work_file(discord_thread_workspace) -> None:
    work_dir = (
        discord_thread_workspace
        / "discord/guilds/guild-1/channels/channel-1__channel-1/"
        "threads/thread-1__thread-1/work"
    )
    work_dir.mkdir(parents=True)
    (work_dir / "jungsi_class_assignments.md").write_text(
        "# 2027 정시반 편성표\n\n"
        "국민대반: 박세영, 최혜은\n"
        "숭실대반 - 박세영, 최재원, 윤지언\n",
        encoding="utf-8",
    )

    result = json.loads(
        _thread_roster_lookup_tool_handler({"roster_names": ["국민대 반", "숭실대반"]})
    )

    assert result["found"] is True
    assert result["rosters"]["국민대반"] == ["박세영", "최혜은"]
    assert result["rosters"]["숭실대반"] == ["박세영", "최재원", "윤지언"]
    assert result["duplicates"] == {"박세영": ["국민대반", "숭실대반"]}


@pytest.mark.asyncio
async def test_natural_router_can_answer_thread_roster_from_tool(discord_thread_workspace) -> None:
    work_dir = (
        discord_thread_workspace
        / "discord/guilds/guild-1/channels/channel-1__channel-1/"
        "threads/thread-1__thread-1/work"
    )
    work_dir.mkdir(parents=True)
    (work_dir / "class_rosters.md").write_text(
        "## 국민대반\n- 박세영\n- 최혜은\n\n## 숭실대반\n- 박세영\n- 윤지언\n",
        encoding="utf-8",
    )

    async def resolver(_messages: list[dict[str, str]]) -> object:
        return _Response(
            router_execute(
                "academy_thread_roster_lookup",
                {"roster_names": ["국민대반", "숭실대반"]},
                confidence=0.96,
            )
        )

    route = await resolve_and_execute_academy_request(
        "국민대 반 숭실대반 명단 줘봐",
        resolver=resolver,
        context_key="discord:guild-1:thread-1:thread-1:user-1",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert "박세영" in route.response_text
    assert "근거가 없어" not in route.response_text
    assert "DB" not in route.response_text
