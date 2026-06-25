"""Discord e2e smoke for governed artifact delivery."""

from __future__ import annotations

import asyncio
import importlib
import json
from unittest.mock import AsyncMock

import pytest

from gateway.platforms.base import SendResult
from tests.e2e.conftest import (
    E2E_MESSAGE_SETTLE_DELAY,
    make_discord_message,
    make_fake_dm_channel,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("filename", ["reviewed-report.xlsx", "archive.mhtml"])
async def test_discord_contract_media_tag_reaches_send_document(
    discord_setup,
    monkeypatch,
    tmp_path,
    filename,
) -> None:
    adapter, runner = discord_setup
    artifact = tmp_path / filename
    artifact.write_bytes(b"PK\x03\x04 fake workbook")
    monkeypatch.setenv("MIHO_MEDIA_ALLOW_DIRS", str(tmp_path))

    import tools.media_delivery_contract_tool as contract_tool

    importlib.reload(contract_tool)
    payload = json.loads(
        contract_tool.media_delivery_contract_tool(
            {
                "artifact_path": str(artifact),
                "caption": "검수된 엑셀 파일입니다.",
            }
        )
    )
    assert payload["reviewer"]["status"] == "pass"

    runner._handle_message_with_agent.return_value = payload["delivery_text"]
    adapter.send_document = AsyncMock(
        return_value=SendResult(success=True, message_id="doc-1")
    )

    msg = make_discord_message(
        content="엑셀 파일 첨부해줘",
        channel=make_fake_dm_channel(),
        mentions=[],
    )
    await adapter._handle_message(msg)
    for _ in range(30):
        if adapter.send.await_count and adapter.send_document.await_count:
            break
        await asyncio.sleep(E2E_MESSAGE_SETTLE_DELAY / 3)

    runner._handle_message_with_agent.assert_awaited_once()
    adapter.send.assert_awaited_once()
    assert "MEDIA:" not in adapter.send.await_args.kwargs["content"]
    adapter.send_document.assert_awaited_once()
    kwargs = adapter.send_document.await_args.kwargs
    assert kwargs["file_path"] == str(artifact.resolve())
    assert kwargs["chat_id"] == str(msg.channel.id)
