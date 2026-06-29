"""Regression: final-send failures must not leave a chat silent."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)
from gateway.session import SessionSource, build_session_key


class _StubAdapter(BasePlatformAdapter):
    def __init__(self):
        super().__init__(PlatformConfig(enabled=True, token="t"), Platform.DISCORD)
        self.sent = []

    async def connect(self):
        return True

    async def disconnect(self):
        return None

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append(
            {
                "chat_id": chat_id,
                "content": content,
                "reply_to": reply_to,
                "metadata": metadata,
            }
        )
        return SendResult(success=True, message_id="fallback")

    async def get_chat_info(self, chat_id):
        return {}


def _event(text="do work"):
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        message_id="m1",
        source=SessionSource(
            platform=Platform.DISCORD,
            chat_id="42",
            chat_type="thread",
            thread_id="99",
        ),
    )


def _session_key():
    return build_session_key(
        SessionSource(
            platform=Platform.DISCORD,
            chat_id="42",
            chat_type="thread",
            thread_id="99",
        )
    )


@pytest.mark.asyncio
async def test_final_text_send_failure_sends_small_visible_notice():
    adapter = _StubAdapter()
    adapter._send_with_retry = AsyncMock(
        return_value=SendResult(success=False, error="message too long")
    )

    async def handler(event):
        return "완성된 최종 답변"

    adapter._message_handler = handler

    await adapter.handle_message(_event())

    sk = _session_key()
    for _ in range(50):
        if sk not in adapter._active_sessions:
            break
        await asyncio.sleep(0.01)

    await adapter.cancel_background_tasks()

    adapter._send_with_retry.assert_awaited_once()
    assert adapter.sent, "final-send failure should produce a visible fallback notice"
    assert "최종 답변 전송에 실패" in adapter.sent[0]["content"]
    assert adapter.sent[0]["chat_id"] == "42"
    assert adapter.sent[0]["metadata"]["thread_id"] == "99"
