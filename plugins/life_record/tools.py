"""Tool handlers for life record workflows."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from pathlib import Path
from typing import Any

from .context import THREAD_ID, current_life_record_dir
from .service import (
    confirm_and_promote,
    delete_life_record_bundle,
    ingest_life_record,
    lookup_student,
    search_life_record,
    summarize_life_record,
    verify_latest,
)


PRIVACY_POLICY = {
    "storage": "thread_scoped_sqlite + central_on_confirm",
    "long_term_memory": "disabled",
    "discord_rag": "disabled",
    "delete_scope": "pdf_db_photos_reviews_exports",
    "pii": "주민번호 뒷자리 미저장(앞6자리=생년월일만)",
}


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from a sync tool handler, whether or not a gateway
    event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro)).result()


def _ingest_pdf_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    try:
        result = _run_async(
            ingest_life_record(
                Path(str(payload.get("pdf_path") or "")).expanduser(),
                current_life_record_dir(),
                source_thread=THREAD_ID.get(),
            )
        )
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
            "consensus_complete": result["consensus_complete"],
            "promoted": result["promoted"],
            "runs": result["runs"],
            "assistant_guidance": "합의되지 않은(needs_review) 항목은 확정 표현 금지. 전부 합의되면 중앙DB로 승격되어 학생 단위 조회가 가능해.",
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


def _lookup_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    query = str(payload.get("query") or "").strip()
    if not query:
        return _json({"ok": False, "message": "학생 이름이나 학교로 검색해줘.", "privacy": PRIVACY_POLICY})
    result = lookup_student(query, limit=int(payload.get("limit") or 10))
    result["privacy"] = PRIVACY_POLICY
    return _json(result)


def _confirm_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    if payload.get("confirm") is not True:
        return _json({"ok": False, "message": "검수 확정은 confirm=true가 필요해.", "privacy": PRIVACY_POLICY})
    document_id = payload.get("document_id")
    result = confirm_and_promote(
        current_life_record_dir(),
        int(document_id) if document_id else None,
        source_thread=THREAD_ID.get(),
    )
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
