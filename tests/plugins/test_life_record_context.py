"""Context recovery tests for life-record tools."""

from __future__ import annotations


def test_current_life_record_dir_recovers_discord_thread_from_session_context(monkeypatch, tmp_path) -> None:
    from gateway.discord_workspace import ensure_workspace
    from gateway.session_context import clear_session_vars, set_session_vars
    from plugins.life_record.context import capture_gateway_context, current_life_record_dir

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    capture_gateway_context(None)
    workspace = ensure_workspace(
        guild_id="guild-1",
        channel_id="channel-1",
        channel_name="10",
        thread_id="thread-a",
        thread_name="thread-a",
    )
    tokens = set_session_vars(platform="discord", chat_id="thread-a", chat_name="thread-a", thread_id="")
    try:
        assert current_life_record_dir() == workspace.active_dir / "life_records"
    finally:
        clear_session_vars(tokens)
