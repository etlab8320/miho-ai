"""Gateway routing tests for 생기부 uploads.

The real Discord gateway should route detected 생기부 documents through the
normal agent/tool loop so the life_record_ingest_pdf tool call is visible and
auditable.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource


def _discord_event(thread_id: str, pdf_path: Path) -> MessageEvent:
    event = MessageEvent(
        text="생기부 저장해놔",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-1",
            chat_id=thread_id,
            parent_chat_id="channel-1",
            guild_id="guild-1",
            chat_name=f"thread-{thread_id}",
        ),
    )
    event.media_urls = [str(pdf_path)]
    event.media_types = ["application/pdf"]
    return event


def _gateway_with_discord_adapter() -> SimpleNamespace:
    return SimpleNamespace(
        _is_user_authorized=lambda _source: True,
        adapters={Platform.DISCORD: object()},
        session_store=None,
    )


def test_life_record_upload_rewrites_to_visible_tool_call(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context
    import plugins.life_record.service as service_module

    pdf = tmp_path / "record.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    async def _yes(_path):
        return True

    async def _must_not_ingest(*_args, **_kwargs):
        raise AssertionError("gateway pre-dispatch must not ingest directly")

    monkeypatch.setattr(service_module, "looks_like_life_record", _yes)
    monkeypatch.setattr(service_module, "ingest_life_record", _must_not_ingest)

    result = asyncio.run(
        _capture_gateway_context(
            _discord_event("thread-life-record", pdf),
            gateway=_gateway_with_discord_adapter(),
        )
    )

    assert result["action"] == "rewrite"
    assert "life_record_ingest_pdf" in result["text"]
    assert str(pdf) in result["text"]
    assert "검증 상태가 pass가 아니거나" in result["text"]
