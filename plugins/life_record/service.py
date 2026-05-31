"""Service layer for thread-scoped life record tools (vision/consensus based)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .consensus import all_confirmed, reconcile
from .pdf_reader import extract_pdf, render_page_images
from .repository import (
    confirm_rows,
    db_path,
    delete_bundle,
    latest_document,
    lookup_central,
    promote_to_central,
    save_import,
    search_records,
    summary_counts,
)
from .review import write_review_html
from .verifier import run_verification
from .vision_extractor import VisionResolver, extract_life_record, to_data_url

DEFAULT_RUNS = 2
MAX_RUNS = 3
RENDER_ZOOM = 3.0


async def ingest_life_record(
    pdf_path: Path,
    bundle_dir: Path,
    *,
    resolver: VisionResolver | None = None,
    runs: int = DEFAULT_RUNS,
    source_thread: str = "",
) -> dict[str, Any]:
    """Render PDF → vision extract N times → reconcile → (recheck if needed) → save →
    verify → promote confirmed data to the central student DB."""
    _validate_pdf_path(pdf_path)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    images = [to_data_url(png) for png in render_page_images(pdf_path, zoom=RENDER_ZOOM)]
    page_count = len(images)

    results: list[dict[str, Any]] = []
    for _ in range(max(1, runs)):
        results.append(await extract_life_record(images, resolver=resolver))
    consensus = reconcile(results)
    # Unresolved disagreements → one more pass at a time, hard-capped at MAX_RUNS.
    while not all_confirmed(consensus) and len(results) < MAX_RUNS:
        results.append(await extract_life_record(images, resolver=resolver))
        consensus = reconcile(results)

    photo = _safe_photo(pdf_path)
    raw_text = json.dumps(consensus, ensure_ascii=False)
    result = save_import(
        bundle_dir=bundle_dir,
        pdf_path=pdf_path,
        page_count=page_count,
        raw_text=raw_text,
        metadata={"runs": len(results), "render_zoom": RENDER_ZOOM},
        consensus=consensus,
        photo=photo,
        source_thread=source_thread,
    )
    document_id = int(result["document_id"])
    verification = run_verification(Path(result["db_path"]), document_id, consensus=consensus)
    review_path = write_review_html(Path(result["db_path"]), document_id, bundle_dir / "reviews")

    complete = all_confirmed(consensus)
    promoted = None
    if complete:
        promoted = promote_to_central(Path(result["db_path"]), document_id, source_thread=source_thread)

    identity = {field: (consensus["identity"].get(field) or {}).get("value") for field in consensus["identity"]}
    return {
        **result,
        "identity": identity,
        "verification": verification,
        "review_path": review_path,
        "counts": summary_counts(Path(result["db_path"]), document_id),
        "consensus_complete": complete,
        "promoted": promoted,
        "runs": len(results),
    }


def confirm_and_promote(bundle_dir: Path, document_id: int | None = None, *, source_thread: str = "") -> dict[str, Any]:
    """Human confirms remaining needs_review rows, then promote to central."""
    path = db_path(bundle_dir)
    doc = latest_document(path) if document_id is None else None
    target_id = document_id or (int(doc["id"]) if doc else None)
    if target_id is None:
        return {"ok": False, "message": "확정할 문서를 찾지 못했어."}
    changed = confirm_rows(path, target_id)
    promoted = promote_to_central(path, target_id, source_thread=source_thread)
    return {"ok": True, "operation": "life_record.confirm", "confirmed_rows": changed, "promoted": promoted}


def verify_latest(bundle_dir: Path, document_id: int | None = None) -> dict[str, Any]:
    path = db_path(bundle_dir)
    doc = latest_document(path) if document_id is None else None
    target_id = document_id or (int(doc["id"]) if doc else None)
    if target_id is None:
        return {"ok": False, "message": "검증할 문서가 없어."}
    verification = run_verification(path, target_id)
    return {"ok": True, "operation": "life_record.verify", "document_id": target_id, "verification": verification}


def search_life_record(bundle_dir: Path, query: str, *, limit: int = 8) -> dict[str, Any]:
    rows = search_records(db_path(bundle_dir), query, limit=limit)
    return {"ok": True, "operation": "life_record.search", "query": query, "results": rows, "count": len(rows)}


def lookup_student(query: str, *, limit: int = 10) -> dict[str, Any]:
    result = lookup_central(query, limit=limit)
    return {"ok": True, "operation": "life_record.lookup", "query": query, **result}


def summarize_life_record(bundle_dir: Path) -> dict[str, Any]:
    path = db_path(bundle_dir)
    doc = latest_document(path)
    if not doc:
        return {"ok": True, "operation": "life_record.summary", "has_data": False, "message": "현재 스레드에 생기부 DB가 없어."}
    counts = summary_counts(path, int(doc["id"]))
    return {
        "ok": True,
        "operation": "life_record.summary",
        "has_data": True,
        "student": {"name": doc["name"], "school_name": doc["school_name"]},
        "document_id": int(doc["id"]),
        "page_count": doc["page_count"],
        "extraction_method": doc["extraction_method"],
        "counts": counts,
    }


def delete_life_record_bundle(bundle_dir: Path) -> dict[str, Any]:
    removed = delete_bundle(bundle_dir)
    return {"ok": True, "operation": "life_record.delete", "removed": removed}


def _safe_photo(pdf_path: Path) -> Any:
    try:
        return extract_pdf(pdf_path).photo
    except Exception:
        return None


def _validate_pdf_path(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise ValueError(f"PDF 경로를 찾을 수 없어: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("생기부는 PDF 파일이어야 해.")
