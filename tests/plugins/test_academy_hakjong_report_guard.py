"""Safety guards for premium hakjong report delivery."""

from __future__ import annotations

import json


def test_hakjong_report_guard_blocks_extra_tools_after_media_package() -> None:
    from plugins.academy_ops.hakjong_report_guard import (
        _block_after_hakjong_report_package,
        _reset_hakjong_report_package_state,
        _track_hakjong_report_package_result,
    )

    _reset_hakjong_report_package_state()
    _track_hakjong_report_package_result(
        tool_name="academy_hakjong_report_package",
        result=json.dumps({"ok": True, "media_tag": "MEDIA:/tmp/report.pdf"}),
        session_id="session-a",
    )

    blocked = _block_after_hakjong_report_package(
        tool_name="read_file",
        args={"path": "/tmp/report.html"},
        session_id="session-a",
    )

    assert blocked and blocked["action"] == "block"
    assert "academy_hakjong_report_package" in blocked["message"]
    assert _block_after_hakjong_report_package(
        tool_name="academy_hakjong_report_package",
        args={},
        session_id="session-a",
    ) is None
    assert _block_after_hakjong_report_package(
        tool_name="send_message",
        args={"text": "MEDIA:/tmp/report.pdf"},
        session_id="session-a",
    ) is None


def test_hakjong_report_guard_blocks_after_package_through_session_context() -> None:
    from gateway.session_context import clear_session_vars, set_session_vars
    from plugins.academy_ops.hakjong_report_guard import (
        _block_after_hakjong_report_package,
        _reset_hakjong_report_package_state,
        _track_hakjong_report_package_result,
    )

    _reset_hakjong_report_package_state()
    tokens = set_session_vars(platform="discord", chat_id="thread-a")
    try:
        _track_hakjong_report_package_result(
            tool_name="academy_hakjong_report_package",
            result=json.dumps({"ok": True, "media_tag": "MEDIA:/tmp/report.pdf"}),
            session_id="session-a",
            task_id="default",
        )

        blocked = _block_after_hakjong_report_package(
            tool_name="skill_view",
            args={},
            task_id="default",
        )
    finally:
        clear_session_vars(tokens)

    assert blocked and blocked["action"] == "block"
    assert "MEDIA" in blocked["message"]


def test_hakjong_report_guard_does_not_global_lock_default_task() -> None:
    from gateway.session_context import clear_session_vars, set_session_vars
    from plugins.academy_ops.hakjong_report_guard import (
        _block_after_hakjong_report_package,
        _reset_hakjong_report_package_state,
        _track_hakjong_report_package_result,
    )

    _reset_hakjong_report_package_state()
    tokens = set_session_vars(platform="discord", chat_id="thread-a")
    try:
        _track_hakjong_report_package_result(
            tool_name="academy_hakjong_report_package",
            result=json.dumps({"ok": True, "media_tag": "MEDIA:/tmp/report.pdf"}),
            task_id="default",
        )
    finally:
        clear_session_vars(tokens)

    other_tokens = set_session_vars(platform="discord", chat_id="thread-b")
    try:
        blocked = _block_after_hakjong_report_package(tool_name="read_file", args={}, task_id="default")
    finally:
        clear_session_vars(other_tokens)

    assert blocked is None


def test_hakjong_report_guard_does_not_lock_after_failed_package() -> None:
    from plugins.academy_ops.hakjong_report_guard import (
        _block_after_hakjong_report_package,
        _reset_hakjong_report_package_state,
        _track_hakjong_report_package_result,
    )

    _reset_hakjong_report_package_state()
    _track_hakjong_report_package_result(
        tool_name="academy_hakjong_report_package",
        result=json.dumps({"ok": False, "errors": ["template missing"]}),
        session_id="session-a",
    )

    assert _block_after_hakjong_report_package(
        tool_name="read_file",
        args={"path": "/tmp/report.html"},
        session_id="session-a",
    ) is None


def test_hakjong_report_guard_blocks_unrelated_tools_on_required_route() -> None:
    from plugins.academy_ops.context import capture_gateway_context
    from plugins.academy_ops.hakjong_report_guard import (
        _block_after_hakjong_report_package,
        _reset_hakjong_report_package_state,
    )

    class Source:
        chat_id = "thread-a"
        user_id = "user-a"
        guild_id = "guild-a"

    class Event:
        source = Source()
        text = "[Miho decision twin] required_tool=academy_hakjong_report_package"

    _reset_hakjong_report_package_state()
    capture_gateway_context(Event())

    blocked = _block_after_hakjong_report_package(tool_name="execute_code", args={}, session_id="session-a")

    assert blocked and blocked["action"] == "block"
    assert _block_after_hakjong_report_package(
        tool_name="academy_hakjong_report_package",
        args={},
        session_id="session-a",
    ) is None


def test_hakjong_report_guard_blocks_required_route_marked_by_event_key() -> None:
    from gateway.session_context import clear_session_vars, set_session_vars
    from plugins.academy_ops.hakjong_report_guard import (
        _block_after_hakjong_report_package,
        _reset_hakjong_report_package_state,
        mark_hakjong_report_required_route,
    )

    class Source:
        chat_id = "thread-a"
        thread_id = ""
        parent_chat_id = "channel-a"

    class Event:
        source = Source()
        text = "가은이 4개 대학 프리미엄 학종 리포트 파일로 보내줘"

    _reset_hakjong_report_package_state()
    mark_hakjong_report_required_route(Event(), required_tool="academy_hakjong_report_package")
    tokens = set_session_vars(platform="discord", chat_id="thread-a", thread_id="")
    try:
        blocked = _block_after_hakjong_report_package(tool_name="terminal", args={})
    finally:
        clear_session_vars(tokens)

    assert blocked and blocked["action"] == "block"
    assert "프리미엄 학종 리포트 계약" in blocked["message"]
