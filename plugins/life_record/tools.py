"""Tool handlers for life record workflows."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from pathlib import Path
from typing import Any

from .context import THREAD_ID, current_life_record_dir, user_requested_life_record_confirm
from .service import (
    confirm_and_promote,
    delete_life_record_bundle,
    ingest_life_record,
    lookup_student,
    search_life_record,
    summarize_life_record,
    verify_latest,
)
from .repository import db_path, document_by_id, latest_document, apply_review_decisions, pending_review_items
from .source_policy import ACCEPTED_SOURCE_TYPES, SOURCE_FILE_ERROR_MESSAGE


logger = logging.getLogger(__name__)


PRIVACY_POLICY = {
    "storage": "thread_scoped_sqlite + central_on_confirm",
    "long_term_memory": "disabled",
    "discord_rag": "disabled",
    "delete_scope": "pdf_db_photos_reviews_exports",
    "pii": "주민번호 뒷자리 미저장(앞6자리=생년월일만)",
}
LIFE_RECORD_INGEST_TIMEOUT_SECONDS = 120.0


def _run_async(coro: Any, *, timeout_seconds: float | None = None) -> Any:
    """Run an async coroutine from a sync tool handler, whether or not a gateway
    event loop is already running."""
    async def _bounded() -> Any:
        if timeout_seconds is None:
            return await coro
        return await asyncio.wait_for(coro, timeout=max(0.001, timeout_seconds))

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_bounded())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_bounded())).result()


def _ingest_pdf_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    try:
        result = _run_async(
            ingest_life_record(
                Path(str(payload.get("pdf_path") or "")).expanduser(),
                current_life_record_dir(),
                source_thread=THREAD_ID.get(),
            ),
            timeout_seconds=LIFE_RECORD_INGEST_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return _json({
            "ok": False,
            "message": (
                "생기부 처리 시간이 길어져 안전하게 중단했어. "
                "원본 파일 상태를 확인한 뒤 새 메시지에서 다시 시도해줘."
            ),
            "human_review_required": True,
            "privacy": PRIVACY_POLICY,
        })
    except (OSError, ValueError, RuntimeError) as exc:
        logger.warning("life_record ingest failed: %s", exc)
        return _json({
            "ok": False,
            "message": SOURCE_FILE_ERROR_MESSAGE,
            "replacement_document_required": True,
            "accepted_source_types": list(ACCEPTED_SOURCE_TYPES),
            "privacy": PRIVACY_POLICY,
        })
    if result.get("ok") is False:
        return _json({**result, "privacy": PRIVACY_POLICY})
    return _json(
        {
            "ok": True,
            "operation": "life_record.ingest_pdf",
            "privacy": PRIVACY_POLICY,
            "db_path": result["db_path"],
            "document_id": result["document_id"],
            "student": result["identity"],
            "stored_pdf_path": result["stored_pdf_path"],
            "source_document_path": result.get("source_document_path"),
            "stored_original_path": result.get("stored_original_path"),
            "converted_pdf_path": result.get("converted_pdf_path"),
            "mhtml_table_count": result.get("mhtml_table_count"),
            "photo_paths": result["photo_paths"],
            "review_path": result["review_path"],
            "counts": result["counts"],
            "verification": result["verification"],
            "consensus_complete": result["consensus_complete"],
            "promoted": result["promoted"],
            "runs": result["runs"],
            "backup_path": result.get("backup_path"),
            "assistant_guidance": "합의되지 않은(needs_review) 항목은 확정 표현을 하지 마세요. life_record_review를 호출해 원장님께 확인이 필요한 항목만 쉬운 말로 안내하고, 전부 검수된 뒤에만 중앙DB로 승격할 수 있습니다.",
        }
    )


def _verify_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    document_id = payload.get("document_id")
    result = verify_latest(current_life_record_dir(), int(document_id) if document_id else None)
    result["privacy"] = PRIVACY_POLICY
    return _json(result)


def _review_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    """Create a short, Discord-ready list of only the rows a human must check."""
    payload = args or {}
    path = db_path(current_life_record_dir())
    requested_id = payload.get("document_id")
    document = document_by_id(path, int(requested_id)) if requested_id else latest_document(path)
    if not document:
        return _json({"ok": False, "message": "현재 스레드에서 검수할 생기부를 찾지 못했습니다.", "privacy": PRIVACY_POLICY})
    document_id = int(document["id"])
    items = pending_review_items(path, document_id)
    public_items = [{key: value for key, value in item.items() if not key.startswith("_")} for item in items]
    return _json(
        {
            "ok": True,
            "operation": "life_record.review",
            "document_id": document_id,
            "items": public_items,
            "remaining_count": len(items),
            "discord_message": _discord_review_message(document, public_items),
            "assistant_guidance": (
                "Discord에는 discord_message만 자연스럽게 전달하세요. DB 경로·행 ID·신뢰도·내부 상태는 말하지 마세요. "
                "원장님의 실제 답변(예: '1번 맞음', '2번 과목명: 국어', '3번 점수: 92점', '4번 저장 안 함')을 받은 뒤에만 "
                "life_record_apply_review를 호출하세요."
            ),
            "privacy": PRIVACY_POLICY,
        }
    )


def _apply_review_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    """Apply explicit, plain-language human review answers to pending rows."""
    payload = args or {}
    decisions = payload.get("decisions")
    if not isinstance(decisions, list) or not all(isinstance(item, dict) for item in decisions):
        return _json({"ok": False, "message": "원장님이 확인한 항목과 답변이 필요합니다.", "privacy": PRIVACY_POLICY})
    path = db_path(current_life_record_dir())
    requested_id = payload.get("document_id")
    document = document_by_id(path, int(requested_id)) if requested_id else latest_document(path)
    if not document:
        return _json({"ok": False, "message": "현재 스레드에서 검수할 생기부를 찾지 못했습니다.", "privacy": PRIVACY_POLICY})
    result = apply_review_decisions(path, int(document["id"]), decisions)
    result["privacy"] = PRIVACY_POLICY
    if result.get("ok"):
        result["next_step"] = (
            "남은 확인 항목이 있으면 life_record_review로 다시 안내하세요. "
            "남은 항목이 0이고 원장님이 최종 저장을 명시적으로 요청할 때만 life_record_confirm을 호출하세요."
        )
    return _json(result)


def _discord_review_message(document: dict[str, Any], items: list[dict[str, Any]]) -> str:
    name = str(document.get("name") or "학생")
    if not items:
        return f"{name} 학생 생기부에서 추가로 확인할 항목은 없습니다. 원본을 모두 대조하셨다면 ‘검수 확정해 주세요’라고 말씀해 주세요."
    lines = [
        f"{name} 학생 생기부에서 원본 확인이 필요한 부분이 {len(items)}개 있습니다.",
        "아래 항목만 원본과 대조해 주세요. 엑셀이나 서버 화면을 보실 필요는 없습니다.",
    ]
    for item in items:
        lines.extend(
            [
                f"\n{item['number']}. [{item['kind']}] {item['label']}",
                f"   현재 읽힌 값: {item['current_value']}",
                f"   맞으면 ‘{item['number']}번 맞음’, 수정이면 ‘{item['number']}번 수정: 정확한 값’, 제외면 ‘{item['number']}번 저장 안 함’이라고 답해 주세요.",
            ]
        )
    lines.append("\n예: ‘1번 과목명은 국어입니다, 2번 점수는 92점입니다, 3번 저장 안 함’")
    return "\n".join(lines)


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
    if not user_requested_life_record_confirm():
        return _json({
            "ok": False,
            "message": "원본을 사람이 확인했다는 명시 요청이 없어서 확정/중앙DB 승격을 막았어. 원본 대조 후 '검수 확정해줘'라고 다시 요청해줘.",
            "privacy": PRIVACY_POLICY,
        })
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
