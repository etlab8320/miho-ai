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
