from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource
from miho_cli.goals import CONTINUATION_PROMPT_TEMPLATE


class FakeAdapter:
    def __init__(self):
        self.calls = []
        self.callbacks = {}
        self._active_sessions = {}

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.calls.append(
            {
                "chat_id": chat_id,
                "content": content,
                "reply_to": reply_to,
                "metadata": metadata,
            }
        )
        return SimpleNamespace(success=True)

    def register_post_delivery_callback(self, session_key, callback, *, generation=None):
        self.callbacks[session_key] = (generation, callback)


def _goal_continuation_event(source, goal="finish the task"):
    return MessageEvent(
        text=CONTINUATION_PROMPT_TEMPLATE.format(goal=goal),
        message_type=MessageType.TEXT,
        source=source,
    )


def _assert_thread_metadata_call(call):
    assert call["chat_id"] == "parent-channel"
    assert call["content"] == "✓ Goal achieved: done"
    assert call["reply_to"] is None
    metadata = call["metadata"]
    assert metadata["thread_id"] == "thread-123"
    assert len(metadata["media_delivery_roots"]) == 1
    assert "thread-123__thread-123" in metadata["media_delivery_roots"][0]


@pytest.mark.asyncio
async def test_goal_status_notice_uses_adapter_send_with_thread_metadata():
    """Regression: /goal judge status must use BasePlatformAdapter.send().

    The old implementation checked for a non-existent send_message() method,
    so the goal could be marked done in state_meta without the visible
    "✓ Goal achieved" status line being delivered to Discord/Telegram.
    """
    runner = GatewayRunner.__new__(GatewayRunner)
    adapter = FakeAdapter()
    runner.adapters = {Platform.DISCORD: adapter}

    source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="parent-channel",
        thread_id="thread-123",
    )

    await runner._send_goal_status_notice(source, "✓ Goal achieved: done")

    assert len(adapter.calls) == 1
    _assert_thread_metadata_call(adapter.calls[0])


@pytest.mark.asyncio
async def test_goal_status_notice_defers_until_post_delivery_callback():
    """Regression: goal status must appear after the agent's visible reply.

    _post_turn_goal_continuation runs before BasePlatformAdapter sends the
    returned final response. It should therefore register a post-delivery
    callback, not send the judge status immediately.
    """
    runner = GatewayRunner.__new__(GatewayRunner)
    adapter = FakeAdapter()
    runner.adapters = {Platform.DISCORD: adapter}
    runner.config = SimpleNamespace(group_sessions_per_user=True, thread_sessions_per_user=False)

    source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="parent-channel",
        thread_id="thread-123",
        user_id="user-1",
    )

    await runner._defer_goal_status_notice_after_delivery(source, "✓ Goal achieved: done")

    assert adapter.calls == []
    assert len(adapter.callbacks) == 1

    _, callback = next(iter(adapter.callbacks.values()))
    result = callback()
    if hasattr(result, "__await__"):
        await result

    assert len(adapter.calls) == 1
    _assert_thread_metadata_call(adapter.calls[0])


def test_clear_goal_pending_continuations_removes_slot_and_overflow_only():
    """Regression: /goal pause/clear must cancel queued self-continuations.

    A user-issued /goal pause can arrive after the judge queued the next
    continuation but before that queued turn runs.  The queued synthetic goal
    continuation should be removed without dropping normal user /queue items.
    """
    runner = GatewayRunner.__new__(GatewayRunner)
    adapter = FakeAdapter()
    adapter._pending_messages = {}
    runner._queued_events = {}

    source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="parent-channel",
        thread_id="thread-123",
    )
    session_key = "discord:parent-channel:thread-123"
    normal_event = MessageEvent(
        text="normal queued user message",
        message_type=MessageType.TEXT,
        source=source,
    )

    adapter._pending_messages[session_key] = _goal_continuation_event(source)
    runner._queued_events[session_key] = [
        normal_event,
        _goal_continuation_event(source, goal="second continuation"),
    ]

    removed = runner._clear_goal_pending_continuations(session_key, adapter)

    assert removed == 2
    assert adapter._pending_messages.get(session_key) is None
    assert runner._queued_events[session_key] == [normal_event]
