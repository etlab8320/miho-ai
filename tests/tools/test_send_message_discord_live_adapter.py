"""Discord send_message routing should prefer the live gateway adapter."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gateway.config import Platform
from tools.send_message_tool import _send_to_platform


def test_discord_send_to_platform_prefers_live_adapter(monkeypatch) -> None:
    sent: list[dict[str, object]] = []

    class LiveDiscordAdapter:
        async def send(self, *, chat_id, content, metadata=None):
            sent.append({"chat_id": chat_id, "content": content, "metadata": metadata})
            return SimpleNamespace(success=True, message_id="live-discord-1")

    async def forbidden_standalone(*_args, **_kwargs):
        raise AssertionError("Discord standalone sender must not run before live adapter")

    runner = SimpleNamespace(adapters={Platform.DISCORD: LiveDiscordAdapter()})
    monkeypatch.setattr("gateway.run._gateway_runner_ref", lambda: runner)

    from gateway.platform_registry import platform_registry
    from miho_cli.plugins import discover_plugins

    discover_plugins()
    entry = platform_registry.get("discord")
    original = entry.standalone_sender_fn
    entry.standalone_sender_fn = forbidden_standalone
    try:
        result = asyncio.run(
            _send_to_platform(
                Platform.DISCORD,
                SimpleNamespace(enabled=True, token="", extra={}),
                "1507988401171857521",
                "라이브 디스코드 전송 검증",
                thread_id="1508130890813800508",
            )
        )
    finally:
        entry.standalone_sender_fn = original

    assert result == {"success": True, "message_id": "live-discord-1"}
    assert sent == [
        {
            "chat_id": "1507988401171857521",
            "content": "라이브 디스코드 전송 검증",
            "metadata": {"thread_id": "1508130890813800508"},
        }
    ]


def test_discord_live_adapter_sends_pdf_attachment(monkeypatch, tmp_path) -> None:
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"%PDF-1.4\n%%EOF\n")
    documents: list[dict[str, object]] = []

    class LiveDiscordAdapter:
        platform = Platform.DISCORD

        async def send(self, *, chat_id, content, metadata=None):
            return SimpleNamespace(success=True, message_id="live-text-1")

        async def send_document(self, *, chat_id, file_path, metadata=None, **_kwargs):
            documents.append({"chat_id": chat_id, "file_path": file_path, "metadata": metadata})
            return SimpleNamespace(success=True, message_id="live-pdf-1")

    async def forbidden_standalone(*_args, **_kwargs):
        raise AssertionError("PDF delivery should use the live Discord adapter")

    runner = SimpleNamespace(adapters={Platform.DISCORD: LiveDiscordAdapter()})
    monkeypatch.setattr("gateway.run._gateway_runner_ref", lambda: runner)

    from gateway.platform_registry import platform_registry
    from miho_cli.plugins import discover_plugins

    discover_plugins()
    entry = platform_registry.get("discord")
    original = entry.standalone_sender_fn
    entry.standalone_sender_fn = forbidden_standalone
    try:
        result = asyncio.run(
            _send_to_platform(
                Platform.DISCORD,
                SimpleNamespace(enabled=True, token="", extra={}),
                "1507988401171857521",
                "PDF 첨부 검증",
                thread_id="1508130890813800508",
                media_files=[(str(artifact), False)],
                force_document=True,
            )
        )
    finally:
        entry.standalone_sender_fn = original

    assert result == {"success": True, "message_id": "live-pdf-1"}
    assert documents == [
        {
            "chat_id": "1507988401171857521",
            "file_path": str(artifact),
            "metadata": {"thread_id": "1508130890813800508"},
        }
    ]
