"""Service layer for thread-scoped life record tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .parsers import (
    group_sections,
    parse_attendance,
    parse_identity,
    parse_subject_grades,
    parse_subject_special_notes,
)
from .pdf_reader import extract_pdf
from .repository import db_path, delete_bundle, latest_document, save_import, search_records, summary_counts
from .review import write_review_html
from .verifier import run_verification


def ingest_life_record(pdf_path: Path, bundle_dir: Path) -> dict[str, Any]:
    _validate_pdf_path(pdf_path)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    extracted = extract_pdf(pdf_path)
    identity = parse_identity(
        extracted.page_texts[0] if extracted.page_texts else "",
        extracted.page_texts[-1] if extracted.page_texts else "",
    )
    sections = group_sections(extracted.page_texts)
    result = save_import(
        bundle_dir=bundle_dir,
        pdf_path=pdf_path,
        extracted=extracted,
        identity=identity,
        sections=sections,
        attendance_rows=parse_attendance(extracted.page_texts[0] if extracted.page_texts else ""),
        grade_rows=parse_subject_grades(extracted.page_texts),
        note_rows=parse_subject_special_notes(extracted.page_texts),
    )
    verification = run_verification(Path(result["db_path"]), int(result["document_id"]))
    review_path = write_review_html(Path(result["db_path"]), int(result["document_id"]), bundle_dir / "reviews")
    return {
        **result,
        "identity": identity,
        "verification": verification,
        "review_path": review_path,
        "counts": summary_counts(Path(result["db_path"]), int(result["document_id"])),
    }


def verify_latest(bundle_dir: Path, document_id: int | None = None) -> dict[str, Any]:
    path = db_path(bundle_dir)
    doc = latest_document(path) if document_id is None else _document(path, document_id)
    if not doc:
        return {"ok": False, "message": "현재 스레드에 생기부 DB가 아직 없어."}
    verification = run_verification(path, int(doc["id"]))
    return {"ok": True, "db_path": str(path), "document_id": int(doc["id"]), "student": doc["name"], "verification": verification}


def search_life_record(bundle_dir: Path, query: str, *, limit: int = 8) -> dict[str, Any]:
    path = db_path(bundle_dir)
    doc = latest_document(path)
    if not doc:
        return {"ok": False, "message": "현재 스레드에 생기부 DB가 아직 없어. 먼저 생기부 PDF를 업로드해서 DB화해야 해."}
    rows = search_records(path, query, limit=limit)
    return {
        "ok": True,
        "db_path": str(path),
        "document_id": int(doc["id"]),
        "student": doc["name"],
        "query": query,
        "matches": rows,
        "review_status": "needs_review",
        "assistant_guidance": "검색 결과에 있는 DB 근거만 사용하고, 없는 내용은 없다고 말할 것.",
    }


def summarize_life_record(bundle_dir: Path) -> dict[str, Any]:
    path = db_path(bundle_dir)
    doc = latest_document(path)
    if not doc:
        return {"ok": False, "message": "현재 스레드에 생기부 DB가 아직 없어."}
    counts = summary_counts(path, int(doc["id"]))
    return {
        "ok": True,
        "db_path": str(path),
        "document_id": int(doc["id"]),
        "student": {"name": doc["name"], "school_name": doc["school_name"]},
        "counts": counts,
        "review_status": "needs_review",
        "assistant_guidance": {
            "persona_commentary": True,
            "do_not_invent": True,
            "must_disclose_review_status": True,
            "basis": "thread_scoped_sqlite_only",
        },
    }


def delete_life_record_bundle(bundle_dir: Path) -> dict[str, Any]:
    deleted = delete_bundle(bundle_dir)
    return {"ok": deleted, "deleted_path": str(bundle_dir), "message": "현재 스레드 생기부 DB/원본/사진/검수 파일을 삭제했어." if deleted else "삭제할 생기부 묶음이 없었어."}


def _validate_pdf_path(pdf_path: Path) -> None:
    if not pdf_path.exists() or not pdf_path.is_file():
        raise ValueError(f"PDF 파일을 찾지 못했어: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("생기부 도구는 PDF 파일만 받을 수 있어.")


def _document(path: Path, document_id: int) -> dict[str, Any] | None:
    from .repository import document_by_id

    return document_by_id(path, document_id)
