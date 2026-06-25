"""Core tool wrapper for pixel document evidence operations."""

from __future__ import annotations

from typing import Any

from tools.registry import registry, tool_result


PIXEL_DOCUMENT_SCHEMA = {
    "name": "pixel_document_evidence",
    "description": (
        "Ingest/search/review PDF, web, MHTML, and scanned document evidence by page image. "
        "Use before answering admissions guide tables, score formulas, scanned docs, or any document number that needs source-page grounding."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "ingest", "search", "review"],
                "description": "Operation to perform.",
            },
            "source": {
                "type": "string",
                "description": "Local document path or URL for action=ingest.",
            },
            "document_id": {
                "type": "string",
                "description": "Document id or manifest path for action=search.",
            },
            "query": {
                "type": "string",
                "description": "Search query for page evidence.",
            },
            "evidence": {
                "type": "object",
                "description": "Evidence payload to review.",
            },
            "answer": {
                "type": "string",
                "description": "Optional answer text to review against evidence.",
            },
            "max_pages": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "description": "Maximum pages to render during ingest.",
            },
            "page_range": {
                "type": "string",
                "description": "Optional 1-based PDF page selection for ingest, such as 2, 3-5, or 1,4,8-9. Non-paginated image/HTML/MHTML inputs only support page 1.",
            },
            "ocr_backend": {
                "type": "string",
                "description": "auto, apple_vision, or none.",
            },
            "languages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "OCR languages such as ko-KR and en-US.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": "Maximum search results.",
            },
        },
        "required": ["action"],
    },
}


def pixel_document_evidence_tool(args: dict[str, Any]) -> str:
    action = str(args.get("action") or "").strip().lower()
    try:
        if action == "status":
            from plugins.pixel_documents.service import status_payload

            return _emit(status_payload())
        if action == "ingest":
            source = str(args.get("source") or "").strip()
            if not source:
                return _emit_error("문서 경로 또는 URL이 필요합니다.")
            from plugins.pixel_documents.service import ingest_document

            return _emit(
                ingest_document(
                    source,
                    max_pages=_bounded_int(args.get("max_pages"), default=30, upper=200),
                    ocr_backend=str(args.get("ocr_backend") or "auto"),
                    languages=args.get("languages") if isinstance(args.get("languages"), list) else None,
                    page_range=_optional_text(args.get("page_range")),
                )
            )
        if action == "search":
            document_id = str(args.get("document_id") or "").strip()
            query = str(args.get("query") or "").strip()
            if not document_id:
                return _emit_error("문서 ID 또는 manifest 경로가 필요합니다.")
            if not query:
                return _emit_error("검색어가 필요합니다.")
            from plugins.pixel_documents.service import search_document

            return _emit(search_document(document_id, query, limit=_bounded_int(args.get("limit"), default=5, upper=20)))
        if action == "review":
            from plugins.pixel_documents.service import review_evidence

            return _emit(review_evidence(args.get("evidence") or {}, answer=str(args.get("answer") or "")))
        return _emit_error("알 수 없는 문서 근거 작업입니다. status, ingest, search, review 중 하나를 사용해 주세요.")
    except ValueError as exc:
        return _emit_error(str(exc))
    except Exception:
        return _emit_error("문서 근거 처리 중 문제가 발생했습니다. 입력 경로와 manifest를 확인한 뒤 다시 실행해 주세요.")


def check_pixel_document_requirements() -> bool:
    return True


def _emit(payload: dict[str, Any]) -> str:
    return tool_result(success=bool(payload.get("ok")), **payload)


def _emit_error(message_ko: str) -> str:
    return tool_result(success=False, ok=False, message_ko=message_ko, errors=[message_ko])


def _bounded_int(value: Any, *, default: int, upper: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, upper))


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


registry.register(
    name="pixel_document_evidence",
    toolset="document_evidence",
    schema=PIXEL_DOCUMENT_SCHEMA,
    handler=lambda args, **kw: pixel_document_evidence_tool(args),
    check_fn=check_pixel_document_requirements,
    emoji="DOC",
)
