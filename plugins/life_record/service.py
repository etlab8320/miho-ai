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
from .vision_extractor import (
    VisionResolver,
    default_codex_resolver,
    extract_from_text,
    extract_life_record,
    has_text_layer,
    to_data_url,
)

DEFAULT_RUNS = 2
MAX_RUNS = 3
RENDER_ZOOM = 3.0
HIRES_ZOOM = 4.5  # re-render for the tie-break pass — crisper small digits (성적/주민번호)


async def ingest_life_record(
    pdf_path: Path,
    bundle_dir: Path,
    *,
    resolver: VisionResolver | None = None,
    text_resolver: Any = None,
    runs: int = DEFAULT_RUNS,
    source_thread: str = "",
) -> dict[str, Any]:
    """Ingest a 생기부 PDF. If it has a real text layer, structure that text (scores
    are exact digital text → 100%); otherwise fall back to vision over page images
    with a hi-res majority-vote tie-break. Then save → verify → promote."""
    _validate_pdf_path(pdf_path)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    extracted = extract_pdf(pdf_path)
    page_pngs = render_page_images(pdf_path, zoom=RENDER_ZOOM)  # for the review gallery
    _save_review_pages(bundle_dir, page_pngs)

    results: list[dict[str, Any]] = []
    if has_text_layer(extracted.page_texts):
        # Text-layer PDF: numbers are exact digital text — no OCR drift.
        page_count = len(extracted.page_texts)
        extraction_method = "codex_text_layer_v1"
        for _ in range(max(1, runs)):
            results.append(await extract_from_text(extracted.page_texts, resolver=text_resolver))
        consensus = reconcile(results)
        while not all_confirmed(consensus) and len(results) < MAX_RUNS:
            results.append(await extract_from_text(extracted.page_texts, resolver=text_resolver))
            consensus = reconcile(results)
    else:
        # Scanned PDF (no text): vision over images, hi-res tie-break majority vote.
        images = [to_data_url(png) for png in page_pngs]
        page_count = len(images)
        extraction_method = "codex_vision_gpt5.5_v1"
        for _ in range(max(1, runs)):
            results.append(await extract_life_record(images, resolver=resolver))
        consensus = reconcile(results)
        if not all_confirmed(consensus) and len(results) < MAX_RUNS:
            hi_images = [to_data_url(png) for png in render_page_images(pdf_path, zoom=HIRES_ZOOM)]
            while not all_confirmed(consensus) and len(results) < MAX_RUNS:
                results.append(await extract_life_record(hi_images, resolver=resolver))
                consensus = reconcile(results)

    photo = extracted.photo
    raw_text = json.dumps(consensus, ensure_ascii=False)
    result = save_import(
        bundle_dir=bundle_dir,
        pdf_path=pdf_path,
        page_count=page_count,
        raw_text=raw_text,
        metadata={"runs": len(results), "method": extraction_method},
        consensus=consensus,
        photo=photo,
        extraction_method=extraction_method,
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
    pending_grades = [
        {"grade": g.get("grade"), "semester": g.get("semester"), "subject": g.get("subject"), "raw_score": g.get("raw_score"), "rank_grade": g.get("rank_grade")}
        for g in (consensus.get("grades") or [])
        if g.get("_status") != "confirmed"
    ]
    return {
        **result,
        "identity": identity,
        "verification": verification,
        "review_path": review_path,
        "counts": summary_counts(Path(result["db_path"]), document_id),
        "consensus_complete": complete,
        "promoted": promoted,
        "runs": len(results),
        "pending_grades": pending_grades,
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


async def looks_like_life_record(pdf_path: Path, *, resolver: VisionResolver | None = None) -> bool:
    """Cheap gate: render only the first page and ask the model if it's a 생기부.
    Lets the gateway auto-route any attached PDF without the user naming a tool —
    and without misrouting non-생기부 PDFs (they return no)."""
    images = [to_data_url(png) for png in render_page_images(pdf_path, zoom=2.0, pages=[0])]
    if not images:
        return False
    from . import vision_extractor as _vx

    resolve = resolver or _vx.default_codex_resolver
    answer = await resolve(
        images,
        "이 문서 이미지가 한국 고등학교 '학교생활기록부(생기부/학생부)'인가? 'yes' 또는 'no' 한 단어로만 답해.",
    )
    return "yes" in (answer or "").strip().lower()[:15]


def format_ingest_summary(result: dict[str, Any]) -> str:
    ident = result.get("identity") or {}
    counts = result.get("counts") or {}
    name = ident.get("name") or "학생"
    lines = [f"📄 {name} 생기부를 정리해서 DB에 저장했어."]
    lines.append(
        f"- 성적 {counts.get('subject_grade_rows', 0)} · 세특 {counts.get('special_note_rows', 0)} · "
        f"출결 {counts.get('attendance_rows', 0)} · 수상 {counts.get('award_rows', 0)}"
    )
    pending_grades = result.get("pending_grades") or []
    if pending_grades:
        lines.append(f"\n⚠️ 점수 검수 필요 {len(pending_grades)}건 (원본과 대조해 확정):")
        for g in pending_grades[:12]:
            sem = f"{g.get('semester')}학기" if g.get("semester") else ""
            rank = f" {g.get('rank_grade')}등급" if g.get("rank_grade") else ""
            lines.append(f"  · {g.get('grade')}학년{sem} {g.get('subject')} {g.get('raw_score') or '—'}{rank}")
        if len(pending_grades) > 12:
            lines.append(f"  · …외 {len(pending_grades) - 12}건")
        lines.append("→ 맞으면 life_record_confirm으로 일괄 확정, 틀린 건 말해주면 고칠게.")
    promoted = result.get("promoted")
    if result.get("consensus_complete") and promoted and promoted.get("ok"):
        lines.append("- 전 항목 합의 완료 → 중앙 학생DB에 저장됨 (이후 life_record_lookup으로 조회 가능)")
    if result.get("review_path"):
        lines.append(f"- (PC 상세 검수표·원본 페이지 포함: {result['review_path']})")
    return "\n".join(lines)


def _save_review_pages(bundle_dir: Path, page_pngs: list[bytes]) -> None:
    """Persist rendered pages so the review HTML can show the original beside the
    extracted values — the human confirms needs_review rows against the source."""
    pages_dir = bundle_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for index, png in enumerate(page_pngs):
        (pages_dir / f"p{index + 1:02d}.png").write_bytes(png)


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
