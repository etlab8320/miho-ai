"""Tool handlers for life record workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import current_life_record_dir
from .service import (
    delete_life_record_bundle,
    ingest_life_record,
    search_life_record,
    summarize_life_record,
    verify_latest,
)


PRIVACY_POLICY = {
    "storage": "thread_scoped_sqlite",
    "long_term_memory": "disabled",
    "discord_rag": "disabled",
    "delete_scope": "pdf_db_photos_reviews_exports",
}


def _ingest_pdf_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    try:
        result = ingest_life_record(Path(str(payload.get("pdf_path") or "")).expanduser(), current_life_record_dir())
    except (OSError, ValueError, RuntimeError) as exc:
        return _json({"ok": False, "message": str(exc), "privacy": PRIVACY_POLICY})
    return _json(
        {
            "ok": True,
            "operation": "life_record.ingest_pdf",
            "privacy": PRIVACY_POLICY,
            "db_path": result["db_path"],
            "document_id": result["document_id"],
            "student": result["identity"],
            "stored_pdf_path": result["stored_pdf_path"],
            "photo_paths": result["photo_paths"],
            "review_path": result["review_path"],
            "counts": result["counts"],
            "verification": result["verification"],
            "assistant_guidance": "생기부 내용은 현재 스레드 DB 근거로만 말하고, 검수 전 확정 표현을 피할 것.",
        }
    )


def _verify_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    document_id = payload.get("document_id")
    result = verify_latest(current_life_record_dir(), int(document_id) if document_id else None)
    result["privacy"] = PRIVACY_POLICY
    return _json(result)


def _search_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    query = str(payload.get("query") or "").strip()
    if not query:
        return _json({"ok": False, "message": "검색어가 필요해.", "privacy": PRIVACY_POLICY})
    result = search_life_record(current_life_record_dir(), query, limit=int(payload.get("limit") or 8))
    result["privacy"] = PRIVACY_POLICY
    return _json(result)


def _summary_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    result = summarize_life_record(current_life_record_dir())
    result["privacy"] = PRIVACY_POLICY
    return _json(result)


def _delete_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    if payload.get("confirm_delete") is not True:
        return _json({"ok": False, "message": "삭제는 확인이 필요해. confirm_delete=true로 다시 실행해야 해.", "privacy": PRIVACY_POLICY})
    result = delete_life_record_bundle(current_life_record_dir())
    result["privacy"] = PRIVACY_POLICY
    return _json(result)


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
