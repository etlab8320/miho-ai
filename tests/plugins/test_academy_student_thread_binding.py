from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


class _Platform:
    value = "discord"


def _source(*, thread_name: str = "김민수", channel_name: str = "수시") -> SimpleNamespace:
    return SimpleNamespace(
        platform=_Platform(),
        guild_id="guild-1",
        parent_chat_id="channel-1",
        chat_id="thread-1",
        thread_id="thread-1",
        chat_name=thread_name,
        _test_channel_name=channel_name,
    )


@pytest.fixture(autouse=True)
def _isolated_binding_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import plugins.academy_ops.student_thread_binding as binding
    import plugins.academy_ops.thread_context as thread_context

    monkeypatch.setattr(binding, "_BINDING_DB_OVERRIDE", tmp_path / "bindings.sqlite3")
    monkeypatch.setattr(thread_context, "_DB_PATH_OVERRIDE", tmp_path / "thread_context.sqlite3")
    monkeypatch.setattr(binding, "_workspace_channel_name", lambda source: getattr(source, "_test_channel_name", ""))
    yield
    monkeypatch.setattr(binding, "_BINDING_DB_OVERRIDE", None)
    monkeypatch.setattr(thread_context, "_DB_PATH_OVERRIDE", None)


def test_infers_student_binding_from_susi_thread_name() -> None:
    from plugins.academy_ops.student_thread_binding import get_binding_for_source

    binding = get_binding_for_source(_source(), infer=True)

    assert binding["student_query"] == "김민수"
    assert binding["source"] == "thread_name"


def test_auto_inference_is_limited_to_susi_channel() -> None:
    from plugins.academy_ops.student_thread_binding import get_binding_for_source

    assert get_binding_for_source(_source(channel_name="코딩"), infer=True) == {}


def test_manual_binding_and_clear_blocks_thread_name_reinference() -> None:
    from plugins.academy_ops.student_thread_binding import (
        clear_binding,
        get_binding_for_source,
        save_manual_binding,
    )

    source = _source(thread_name="김민수")
    assert save_manual_binding(source, "박지훈")["student_query"] == "박지훈"
    assert get_binding_for_source(source)["student_query"] == "박지훈"

    clear_binding(source)
    assert get_binding_for_source(source, infer=True) == {}


@pytest.mark.asyncio
async def test_natural_router_fills_default_bound_student_when_llm_omits_student() -> None:
    from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
    from tests.plugins.academy_router_helpers import router_execute

    class _Response:
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(
                    content=router_execute("academy_student_context", {"student_query": ""}, confidence=0.95)
                )
            )
        ]

    async def resolver(_messages):
        return _Response()

    calls: list[dict] = []

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps({"ok": True, "message": f"{args['student_query']} 컨텍스트"}, ensure_ascii=False)

    route = await resolve_and_execute_academy_request(
        "얘 수업 언제야?",
        resolver=resolver,
        handlers={"academy_student_context": handler},
        default_student_query="김민수",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [{"student_query": "김민수", "today": "2026-06-30"}]


def test_thread_delete_cleanup_removes_binding_and_short_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway.discord_workspace import ensure_workspace
    from gateway.discord_workspace_archive import archive_workspace_for_thread
    from plugins.academy_ops.student_thread_binding import get_binding_for_source, save_manual_binding
    from plugins.academy_ops.thread_context import get_thread_context, remember_thread_context

    # Isolate Discord workspace root too.
    monkeypatch.setattr("gateway.discord_workspace_paths.get_miho_home", lambda: tmp_path)
    ensure_workspace(
        guild_id="guild-1",
        channel_id="channel-1",
        channel_name="수시",
        thread_id="thread-1",
        thread_name="김민수",
    )
    source = _source()
    save_manual_binding(source, "김민수")
    remember_thread_context(
        "discord:guild-1:channel-1:thread-1:user-1",
        tool_name="academy_student_context",
        args={"student_query": "김민수"},
        payload={"ok": True, "student": {"name": "김민수"}},
    )

    thread = SimpleNamespace(
        id="thread-1",
        name="김민수",
        parent_id="channel-1",
        parent=SimpleNamespace(id="channel-1"),
        guild=SimpleNamespace(id="guild-1"),
    )
    archived = archive_workspace_for_thread(thread)

    assert archived is not None
    assert archived.exists()
    assert get_binding_for_source(source, infer=False) == {}
    assert get_thread_context("discord:guild-1:channel-1:thread-1:user-1") == {}
