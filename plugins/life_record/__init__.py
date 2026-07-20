"""Thread-scoped Korean school life record tools."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .context import capture_gateway_context
from .tools import (
    _apply_review_tool_handler,
    _confirm_tool_handler,
    _delete_tool_handler,
    _ingest_pdf_tool_handler,
    _lookup_tool_handler,
    _review_tool_handler,
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
        "- PDF/MHTML 업로드 후 `life_record_ingest_pdf`가 현재 Discord 스레드 전용 SQLite DB를 만듭니다.\n"
        "- 스캔본은 저장하지 않고 카카오톡 원본 PDF 또는 나이스플러스 MHTML을 다시 요청합니다.\n"
        "- 원본 파일과 학생 사진은 같은 스레드 폴더에만 보관합니다.\n"
        "- 장기기억/RAG에는 원문을 넣지 않습니다.\n"
        "- 검수 전 데이터는 needs_review로 다룹니다."
    )


_LIFE_RECORD_TOOLS = {
    "life_record_ingest_pdf", "life_record_verify", "life_record_search",
    "life_record_summary", "life_record_delete", "life_record_lookup", "life_record_review",
    "life_record_apply_review", "life_record_confirm",
}
_ROUTE_PRIORITY = 100
# Unique fingerprints of the life-record DB — if a general-purpose tool's args
# contain these, the model is hand-rolling/poking the 생기부 DB directly.
_DB_MARKERS = (
    ".miho/life_records",
    "life_records.sqlite3",
    "central.sqlite3",
    "student_documents",
    "subject_grades",
    "subject_special_notes",
    "attendance_records",
    "central_grades",
    "central_notes",
    "central_attendance",
    "central_awards",
)
def _block_life_record_handcoding(tool_name: Any = None, args: Any = None, **_: Any) -> dict[str, str] | None:
    """pre_tool_call guard: forbid touching the 생기부 DB with execute_code/terminal/
    sqlite. The dedicated life_record_* tools (which legitimately use that DB) pass.
    데이터 무결성 보호만 한다 — 문맥 키워드로 다른 도구를 차단하지 않는다 (의도 판단은 LLM)."""
    name = str(tool_name or "").strip()
    if not name:
        return None
    if name in _LIFE_RECORD_TOOLS:
        return None
    try:
        blob = json.dumps(args or {}, ensure_ascii=False)
    except (TypeError, ValueError):
        return None
    if any(marker in blob for marker in _DB_MARKERS):
        return {
            "action": "block",
            "message": (
                "생기부 데이터는 직접 코드(execute_code·terminal·sqlite)로 만들거나 고치지 마. "
                "반드시 life_record_ingest_pdf(PDF 저장) / life_record_summary·search·lookup(조회) "
                "도구를 사용해. PDF가 있으면 첨부하면 자동으로 처리돼."
            ),
        }
    return None


def _life_record_attachment(event: Any) -> Path | None:
    """Return the first attached supported local document path, if any."""
    from .pdf_reader import is_supported_document_path

    for url in getattr(event, "media_urls", None) or []:
        path = Path(str(url))
        if is_supported_document_path(path):
            return path
    return None


def _is_authorized_for_life_record(gateway: Any, source: Any) -> bool:
    """Whether this sender may have a 생기부 (PII) auto-ingested. The
    pre_gateway_dispatch hook runs BEFORE the gateway's own auth check, so we must
    verify here. Fail-safe: if authorization can't be determined, treat as NOT
    authorized (PII is never auto-processed on an unknown sender)."""
    if gateway is None or source is None:
        return False
    try:
        return bool(gateway._is_user_authorized(source))
    except Exception as exc:  # unknown gateway shape / auth error → deny
        logger.info("life_record auth check failed, treating as unauthorized: %s", exc)
        return False


async def _capture_gateway_context(event: Any = None, gateway: Any = None, **_: Any) -> dict[str, Any]:
    """Capture thread context, and auto-route an attached 생기부 PDF/MHTML straight
    into life_record_ingest_pdf — no tool name or command needed. A document that
    isn't a 생기부 returns 'no' from the vision gate and passes through untouched.

    생기부 is PII, so auto-ingest only fires for an *authorized* sender; otherwise
    the file passes through untouched (the gateway's normal auth/pairing flow runs)."""
    capture_gateway_context(event)
    try:
        urls = getattr(event, "media_urls", None) or []
        document = _life_record_attachment(event)
        if document is None:
            if urls:
                logger.info("life_record pre-dispatch: %d attachment(s), no usable PDF/MHTML: %s", len(urls), urls[:3])
            return {"action": "allow"}
        # PII guard (P1-3): never auto-process a 생기부 from an unauthorized sender.
        if not _is_authorized_for_life_record(gateway, getattr(event, "source", None)):
            logger.info("life_record auto-route skipped: sender not authorized for 생기부 PII")
            return {"action": "allow"}
        logger.info("life_record pre-dispatch: document detected (%s) — running 생기부 vision gate", document.name)
        from .service import looks_like_life_record

        is_lr = await looks_like_life_record(document)
        logger.info("life_record pre-dispatch: looks_like_life_record=%s", is_lr)
        if not is_lr:
            return {"action": "allow"}
        return {
            "action": "rewrite",
            "text": _tool_request_text(event, document),
            "route": "life_record",
            "reason": "supported_document",
            "intent": "life_record.ingest",
            "confidence": 0.99,
            "evidence": ["supported_attachment", document.suffix.lower()],
            "required_tool": "life_record_ingest_pdf",
            "priority": _ROUTE_PRIORITY,
        }
    except Exception as exc:
        logger.warning("life_record private document gate failed: %s", exc)
        return {
            "action": "respond",
            "text": (
                "첨부 문서를 개인정보 보호 방식으로 안전하게 확인하지 못해 자동 처리를 중단했어. "
                "원본 파일 상태를 확인한 뒤 다시 첨부해줘."
            ),
            "route": "life_record",
            "reason": "private_document_gate_failed",
            "intent": "life_record.ingest",
            "confidence": 1.0,
            "priority": _ROUTE_PRIORITY,
        }


def _tool_request_text(event: Any, document: Path) -> str:
    original = str(getattr(event, "text", "") or "").strip()
    path = _agent_visible_path(document)
    return (
        "[생기부 자동 감지]\n"
        "첨부된 파일은 한국 학교생활기록부/생기부로 판정됐다.\n"
        "반드시 일반 답변으로 처리하지 말고 `life_record_ingest_pdf` 도구를 호출해 DB 저장과 검증을 수행해라.\n"
        f"도구 인자: pdf_path={json.dumps(path, ensure_ascii=False)}\n"
        "도구 결과의 document_id, student, counts, verification, review_path를 근거로 답변해라.\n"
        "replacement_document_required=true이면 저장 완료라고 말하지 말고 "
        "카카오톡 원본 PDF 또는 나이스플러스 MHTML을 다시 요청해라.\n"
        "검증 상태가 pass가 아니거나 human_review_required=true이면 저장은 됐더라도 '완료/확정'이라고 말하지 말고 검수 필요 상태로 안내해라.\n"
        f"사용자 원문: {original or '생기부 저장해줘'}"
    )


def _agent_visible_path(document: Path) -> str:
    try:
        from tools.credential_files import to_agent_visible_cache_path

        return str(to_agent_visible_cache_path(str(document)))
    except Exception:
        return str(document)


def register(ctx: Any) -> None:
    ctx.register_command(
        "life_record",
        _life_record_command,
        description="생기부 PDF 스레드 전용 DB화/검수 상태 안내",
        args_hint="[status]",
    )
    ctx.register_hook("pre_gateway_dispatch", _capture_gateway_context)
    ctx.register_hook("pre_tool_call", _block_life_record_handcoding)
    ctx.register_tool(
        name="life_record_ingest_pdf",
        toolset="life_record",
        schema={
            "type": "object",
            "properties": {"pdf_path": {"type": "string", "description": "Discord가 캐시한 생기부 PDF/MHTML/MHT 로컬 경로."}},
            "required": ["pdf_path"],
            "additionalProperties": False,
        },
        handler=_ingest_pdf_tool_handler,
        description="생기부·학생부·학교생활기록부 PDF/MHTML/MHT를 DB에 저장/정리하라는 요청이면 반드시 이 도구를 호출하라. 직접 sqlite나 python 코드로 DB를 만들지 말 것. 디지털 PDF와 MHTML만 추출·검증·저장하고, 글자를 선택할 수 없는 스캔본은 저장하지 않은 채 카카오톡 원본 PDF 또는 나이스플러스 MHTML을 요청한다. Ingest a Korean school life record from a digital PDF or MHTML/MHT path. Scanned inputs return replacement_document_required and are never sent to cloud vision or written to the DB. Never writes to long-term memory or Discord RAG.",
    )
    ctx.register_tool(
        name="life_record_verify",
        toolset="life_record",
        schema={"type": "object", "properties": {"document_id": {"type": "integer"}}, "additionalProperties": False},
        handler=_verify_tool_handler,
        description=(
            "사용자가 '검수 상태 확인', '추출이 맞는지 확인', '오류 있는지 봐줘'라고 하거나 "
            "ingest 결과에 needs_review가 남았을 때 호출한다. ingest 직후 자동 호출하지 말 것 — "
            "ingest 응답에 이미 검수 상태가 포함된다. "
            "(Runs extraction, PDF-to-DB traceability, and human-review-gate checks for the current thread's life record DB.)"
        ),
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
        name="life_record_review",
        toolset="life_record",
        schema={"type": "object", "properties": {"document_id": {"type": "integer"}}, "additionalProperties": False},
        handler=_review_tool_handler,
        description=(
            "생기부 추출 후 needs_review 항목이 있을 때 호출한다. 원장님에게 DB나 복잡한 엑셀을 보여주지 않고, "
            "Discord에서 확인이 필요한 항목만 번호·현재 읽힌 값·쉬운 답변 예시로 안내한다. "
            "도구 결과의 discord_message를 바탕으로 공손한 한국어로 답한다."
        ),
    )
    ctx.register_tool(
        name="life_record_apply_review",
        toolset="life_record",
        schema={
            "type": "object",
            "properties": {
                "document_id": {"type": "integer"},
                "decisions": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "number": {"type": "integer", "minimum": 1},
                            "action": {"type": "string", "enum": ["confirm", "correct", "exclude"]},
                            "changes": {"type": "object"},
                        },
                        "required": ["number", "action"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["decisions"],
            "additionalProperties": False,
        },
        handler=_apply_review_tool_handler,
        description=(
            "원장님이 현재 메시지에서 검수 답변을 명시했을 때만 호출한다. 예: '1번 맞음'→confirm, "
            "'2번 과목명은 국어/점수는 92점'→correct+changes, '3번 저장 안 함'→exclude. "
            "번호는 반드시 직전 life_record_review의 번호를 사용하고, 도구가 반환하지 않은 DB 경로·행 ID·테이블명은 절대 입력하지 않는다."
        ),
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
        description="Human-confirm the current thread document's remaining needs_review rows, then promote the confirmed life record into the central student DB. Only call when the user's current message explicitly says they checked the original/review and wants confirmation (for example: '검수 확정해줘'). Never call after an ingest just because rows need review.",
    )
