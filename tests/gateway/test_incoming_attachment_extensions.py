"""Incoming Discord attachment extension coverage."""

import os

import pytest

from gateway.platforms.base import MessageType
from tests.gateway.test_discord_document_handling import (
    _mock_aiohttp_download,
    adapter,
    make_attachment,
    make_message,
)


@pytest.mark.asyncio
async def test_discord_accepts_korean_office_web_archive_and_legacy_excel_by_default(adapter):
    attachments = [
        make_attachment(filename="생기부.hwp", content_type="application/octet-stream"),
        make_attachment(filename="학종리포트.hwpx", content_type="application/octet-stream"),
        make_attachment(filename="저장본.mhtml", content_type="message/rfc822"),
        make_attachment(filename="성적표.xls", content_type="application/vnd.ms-excel"),
        make_attachment(filename="상담표.numbers", content_type="application/octet-stream"),
    ]

    with _mock_aiohttp_download(b"document bytes"):
        await adapter._handle_message(make_message(attachments, content="검토해줘"))

    event = adapter.handle_message.call_args[0][0]
    assert event.message_type == MessageType.DOCUMENT
    assert len(event.media_urls) == len(attachments)
    assert all(os.path.exists(path) for path in event.media_urls)
    assert event.media_types == [
        "application/x-hwp",
        "application/vnd.hancom.hwpx",
        "message/rfc822",
        "application/vnd.ms-excel",
        "application/vnd.apple.numbers",
    ]
