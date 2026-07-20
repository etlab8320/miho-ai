"""Accepted source policy for Korean school life records."""

from __future__ import annotations

from typing import Any


ACCEPTED_SOURCE_TYPES = ("original_pdf", "neisplus_mhtml")
SCANNED_SOURCE_MESSAGE = (
    "이 파일은 글자를 선택할 수 없는 스캔본이라 정확하게 자동 저장하기 어려워. "
    "카카오톡으로 받은 생기부 원본 PDF 또는 나이스플러스에서 저장한 MHTML 파일을 "
    "다시 첨부해줘. 현재 파일은 외부로 보내거나 DB에 저장하지 않았어."
)
SOURCE_FILE_ERROR_MESSAGE = (
    "생기부 파일을 안전하게 처리하지 못했어. 카카오톡으로 받은 생기부 원본 PDF 또는 "
    "나이스플러스에서 저장한 MHTML 파일을 새 메시지에 다시 첨부해줘."
)


def scanned_source_replacement_required() -> bool:
    """Scanned student records require a digital source by default."""
    return True


def scanned_source_result() -> dict[str, Any]:
    """Return the stable no-write contract for a scanned student record."""
    return {
        "ok": False,
        "operation": "life_record.scanned_source_required",
        "message": SCANNED_SOURCE_MESSAGE,
        "replacement_document_required": True,
        "accepted_source_types": list(ACCEPTED_SOURCE_TYPES),
        "human_review_required": False,
        "db_write_allowed": False,
        "cloud_upload_performed": False,
    }


__all__ = [
    "ACCEPTED_SOURCE_TYPES",
    "SOURCE_FILE_ERROR_MESSAGE",
    "scanned_source_replacement_required",
    "scanned_source_result",
]
