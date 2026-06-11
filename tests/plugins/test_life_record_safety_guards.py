"""Safety guard tests for life-record tools."""

from __future__ import annotations

from types import SimpleNamespace


def _event(text: str, chat_id: str = "thread-a") -> SimpleNamespace:
    source = SimpleNamespace(
        chat_id=chat_id,
        parent_chat_id="channel-1",
        guild_id="guild-1",
        chat_name=chat_id,
    )
    return SimpleNamespace(text=text, source=source)


def test_confirm_requires_explicit_review_phrase() -> None:
    from plugins.life_record.context import capture_gateway_context, user_requested_life_record_confirm

    capture_gateway_context(_event("중앙DB에 유가은 자료가 있는지 봐줘"))
    assert user_requested_life_record_confirm() is False

    capture_gateway_context(_event("원본 대조했고 검수 확정해줘"))
    assert user_requested_life_record_confirm() is True


def test_pre_tool_call_blocks_central_life_record_db_access() -> None:
    from plugins.life_record import _block_life_record_handcoding

    blocked = _block_life_record_handcoding(
        tool_name="terminal",
        args={"command": "sqlite3 ~/.miho/life_records/central.sqlite3 'select * from central_grades'"},
    )

    assert blocked and blocked["action"] == "block"
    assert _block_life_record_handcoding(
        tool_name="life_record_lookup",
        args={"query": "유가은"},
    ) is None
