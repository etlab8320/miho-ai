"""Thread-scoped Korean school life record tools."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .context import THREAD_ID, capture_gateway_context, current_life_record_dir
from .tools import (
    _confirm_tool_handler,
    _delete_tool_handler,
    _ingest_pdf_tool_handler,
    _lookup_tool_handler,
    _search_tool_handler,
    _summary_tool_handler,
    _verify_tool_handler,
)

logger = logging.getLogger(__name__)


def _life_record_command(raw_args: str = "") -> str:
    text = raw_args.strip()
    if text == "status":
        return _summary_tool_handler({})
    return (
        "생기부 도구\n"
        "- PDF 업로드 후 `life_record_ingest_pdf`가 현재 Discord 스레드 전용 SQLite DB를 만듭니다.\n"
        "- 원본 PDF와 학생 사진은 같은 스레드 폴더에만 보관합니다.\n"
        "- 장기기억/RAG에는 원문을 넣지 않습니다.\n"
        "- 검수 전 데이터는 needs_review로 다룹니다."
    )


def _pdf_attachment(event: Any) -> Path | None:
    """Return the first attached PDF's local path, if any."""
    for url in getattr(event, "media_urls", None) or []:
        text = str(url)
        if text.lower().endswith(".pdf") and Path(text).exists():
            return Path(text)
    return None


async def _capture_gateway_context(event: Any = None, **_: Any) -> dict[str, Any]:
    """Capture thread context, and auto-route an attached 생기부 PDF straight into
    life_record_ingest_pdf — no tool name or command needed. A PDF that isn't a
    생기부 returns 'no' from the vision gate and passes through untouched."""
    capture_gateway_context(event)
    try:
        urls = getattr(event, "media_urls", None) or []
        pdf = _pdf_attachment(event)
        if pdf is None:
            if urls:
                logger.info("life_record pre-dispatch: %d attachment(s), no usable PDF: %s", len(urls), urls[:3])
            return {"action": "allow"}
        logger.info("life_record pre-dispatch: PDF detected (%s) — running 생기부 vision gate", pdf.name)
        from .service import format_ingest_summary, ingest_life_record, looks_like_life_record

        is_lr = await looks_like_life_record(pdf)
        logger.info("life_record pre-dispatch: looks_like_life_record=%s", is_lr)
        if not is_lr:
            return {"action": "allow"}
        result = await ingest_life_record(pdf, current_life_record_dir(), source_thread=THREAD_ID.get())
        logger.info("life_record pre-dispatch: auto-ingested document_id=%s", result.get("document_id"))
        return {"action": "respond", "text": format_ingest_summary(result)}
    except Exception as exc:  # never block other plugins on a routing failure
        logger.info("life_record auto-route skipped: %s", exc)
        return {"action": "allow"}


def register(ctx: Any) -> None:
    ctx.register_command(
        "life_record",
        _life_record_command,
        description="생기부 PDF 스레드 전용 DB화/검수 상태 안내",
        args_hint="[status]",
    )
    ctx.register_hook("pre_gateway_dispatch", _capture_gateway_context)
    ctx.register_tool(
        name="life_record_ingest_pdf",
        toolset="life_record",
        schema={
            "type": "object",
            "properties": {"pdf_path": {"type": "string", "description": "Discord가 캐시한 생기부 PDF 로컬 경로."}},
            "required": ["pdf_path"],
            "additionalProperties": False,
        },
        handler=_ingest_pdf_tool_handler,
        description="생기부·학생부·학교생활기록부 PDF를 DB에 저장/정리하라는 요청이면 반드시 이 도구를 호출하라. 직접 sqlite나 python 코드로 DB를 만들지 말 것 — 이 도구가 vision(gpt-5.5) 추출 + 다회 합의 검증 + 중앙 학생DB 승격 + 검수 HTML을 모두 처리한다. Ingest a Korean school life record (생기부) PDF: pass the attached PDF's local path as pdf_path. Handles vision extraction, consensus verification, central student DB promotion, and review HTML. Never hand-roll a DB for 생기부 — always use this tool. Never writes to long-term memory or Discord RAG.",
    )
    ctx.register_tool(
        name="life_record_verify",
        toolset="life_record",
        schema={"type": "object", "properties": {"document_id": {"type": "integer"}}, "additionalProperties": False},
        handler=_verify_tool_handler,
        description="Run extraction, PDF-to-DB traceability, and human-review-gate checks for the current thread's life record DB.",
    )
    ctx.register_tool(
        name="life_record_search",
        toolset="life_record",
        schema={
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8}},
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=_search_tool_handler,
        description="Search only the current Discord thread's life record SQLite DB. Use for 세특, 출결, 행동특성, 수상, 진로, or 상담 evidence lookups.",
    )
    ctx.register_tool(
        name="life_record_summary",
        toolset="life_record",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_summary_tool_handler,
        description="Return safe summary metadata for the current thread's life record DB. The assistant must not invent content beyond DB facts.",
    )
    ctx.register_tool(
        name="life_record_delete",
        toolset="life_record",
        schema={"type": "object", "properties": {"confirm_delete": {"type": "boolean"}}, "required": ["confirm_delete"], "additionalProperties": False},
        handler=_delete_tool_handler,
        description="Delete the current thread's life record bundle: SQLite DB, source PDFs, photos, reviews, and exports. Requires explicit confirmation.",
    )
    ctx.register_tool(
        name="life_record_lookup",
        toolset="life_record",
        schema={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "학생 이름 또는 학교명"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10}},
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=_lookup_tool_handler,
        description="Look up a student in the central life-record DB (confirmed records accumulated across semesters: grades, attendance, awards). Use when asked about a student whose 생기부 was already ingested and confirmed.",
    )
    ctx.register_tool(
        name="life_record_confirm",
        toolset="life_record",
        schema={
            "type": "object",
            "properties": {"confirm": {"type": "boolean"}, "document_id": {"type": "integer"}},
            "required": ["confirm"],
            "additionalProperties": False,
        },
        handler=_confirm_tool_handler,
        description="Human-confirm the current thread document's remaining needs_review rows, then promote the confirmed life record into the central student DB. Requires confirm=true.",
    )
