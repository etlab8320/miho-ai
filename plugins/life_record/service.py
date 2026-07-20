"""Service layer for thread-scoped life record tools (vision/consensus based)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from .consensus import all_confirmed, reconcile
from .docforge_private import read_private_first_page_text
from .mhtml_tables import extract_neis_mhtml_tables
from .mhtml_source import empty_extraction, extract_from_mhtml_source
from .pdf_text_source import extract_from_pdf_text, has_core_pdf_text_data
from .pdf_reader import (
    create_text_pdf,
    convert_mhtml_to_pdf,
    crop_id_photo,
    extract_mhtml_text,
    extract_pdf,
    is_mhtml_path,
    is_supported_document_path,
    preferred_document_suffix,
    render_page_images,
)
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
from .source_policy import (
    scanned_source_replacement_required,
    scanned_source_result,
)
from .verifier import run_verification
from .vision_extractor import (
    VisionResolver,
    default_codex_resolver,
    extract_from_mhtml_text,
    extract_from_text,
    extract_life_record,
    has_text_layer,
    locate_id_photo,
    to_data_url,
)

DEFAULT_RUNS = 2
MAX_RUNS = 3
RENDER_ZOOM = 3.0
HIRES_ZOOM = 4.5  # re-render for the tie-break pass — crisper small digits (성적/주민번호)
MAX_PAGES = 50  # 생기부 is normally 10~30 pages; cap rendering/vision so a huge or
# malformed PDF can't explode memory/time (P2-6). Excess pages are not processed.


async def ingest_life_record(
    pdf_path: Path,
    bundle_dir: Path,
    *,
    resolver: VisionResolver | None = None,
    text_resolver: Any = None,
    runs: int = DEFAULT_RUNS,
    source_thread: str = "",
) -> dict[str, Any]:
    """Ingest a 생기부 PDF or Chrome-saved MHTML/MHT document.

    MHTML uses a source-text fast path first (Chrome-saved MHTML normally embeds
    the full HTML text), then creates/normalizes a PDF only for review/storage.
    PDF inputs keep the existing text-layer/vision/consensus path. Then save →
    verify → promote.
    """
    _validate_document_path(pdf_path)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    source_document_path = pdf_path
    stored_original_path = _store_original_document(bundle_dir, source_document_path) if is_mhtml_path(source_document_path) else None
    mhtml_page_texts = extract_mhtml_text(source_document_path) if is_mhtml_path(source_document_path) else []
    mhtml_tables = _extract_mhtml_tables(source_document_path) if is_mhtml_path(source_document_path) else None
    processing_pdf_path = source_document_path if mhtml_tables else _normalize_to_pdf(source_document_path, bundle_dir, page_texts=mhtml_page_texts)
    extracted = extract_pdf(processing_pdf_path) if not mhtml_tables else None
    render_pages: list[int] | None = None
    if extracted and extracted.page_count > MAX_PAGES:
        logger.warning("life_record: %s has %d pages (> cap %d) — processing only the first %d",
                       processing_pdf_path.name, extracted.page_count, MAX_PAGES, MAX_PAGES)
        render_pages = list(range(MAX_PAGES))
    is_scanned = bool(
        extracted
        and not has_text_layer(mhtml_page_texts)
        and not has_text_layer(extracted.page_texts)
    )
    if is_scanned and resolver is None and scanned_source_replacement_required():
        return scanned_source_result()
    page_pngs = [] if mhtml_tables else render_page_images(processing_pdf_path, zoom=RENDER_ZOOM, pages=render_pages)
    _save_review_pages(bundle_dir, page_pngs)

    results: list[dict[str, Any]] = []
    document_raw_text: str | None = None
    sections: list[dict[str, Any]] = []
    if mhtml_tables:
        page_count = mhtml_tables.table_count
        extraction_method = "neisplus_mhtml_table_v1"
        results = [mhtml_tables.extraction, mhtml_tables.extraction]
        consensus = reconcile(results)
        document_raw_text = mhtml_tables.raw_text
        sections = mhtml_tables.sections
    elif has_text_layer(mhtml_page_texts):
        page_count = len(mhtml_page_texts)
        extraction_method = "neis_mhtml_source_text_v2"
        text_source = mhtml_page_texts
        results.append(extract_from_mhtml_source(text_source))
        if _mhtml_model_pass_enabled() or text_resolver is not None:
            try:
                results.append(await extract_from_mhtml_text(text_source, resolver=text_resolver))
            except Exception as exc:
                logger.warning("life_record: mhtml text model pass failed; storing deterministic review copy: %s", exc)
                results.append(empty_extraction())
        else:
            results.append(empty_extraction())
        consensus = reconcile(results)
    elif has_text_layer(extracted.page_texts):
        # Text-layer PDF: numbers are exact digital text — no OCR drift. The
        # default path must not wait on the auxiliary LLM. Use a deterministic
        # parser first; a bounded model pass is opt-in for manual repair work.
        page_count = len(extracted.page_texts)
        extraction_method = "neis_pdf_text_layer_v1"
        text_source = extracted.page_texts
        document_raw_text = "\n\n".join(text_source)
        deterministic = extract_from_pdf_text(text_source)
        results.append(deterministic)
        if _pdf_model_pass_enabled() or text_resolver is not None:
            try:
                model_result = await extract_from_text(text_source, resolver=text_resolver)
                if has_core_pdf_text_data(deterministic):
                    results.append(model_result)
                else:
                    results = [model_result, model_result.copy()]
            except Exception as exc:
                logger.warning("life_record: pdf text model pass failed; storing deterministic review copy: %s", exc)
                results.append(empty_extraction())
        elif has_core_pdf_text_data(deterministic):
            results.append(deterministic)
        else:
            results.append(empty_extraction())
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
            hi_images = [to_data_url(png) for png in render_page_images(processing_pdf_path, zoom=HIRES_ZOOM, pages=render_pages)]
            while not all_confirmed(consensus) and len(results) < MAX_RUNS:
                results.append(await extract_life_record(hi_images, resolver=resolver))
                consensus = reconcile(results)

    photo = extracted.photo if extracted else None
    # Scanned PDF: the whole page is one image, so extract_pdf grabbed the full page
    # as the "photo". Crop it down to just the ID photo via vision. Text-layer PDFs
    # already embed a clean ID photo, so leave those.
    if extracted and not has_text_layer(mhtml_page_texts) and not has_text_layer(extracted.page_texts):
        try:
            first_page = render_page_images(processing_pdf_path, zoom=2.0, pages=[0])
            if first_page:
                bbox = await locate_id_photo(to_data_url(first_page[0]), resolver=resolver)
                if bbox:
                    cropped = crop_id_photo(processing_pdf_path, bbox)
                    if cropped:
                        photo = cropped
        except Exception:
            pass
    raw_text = document_raw_text or json.dumps(consensus, ensure_ascii=False)
    metadata = {
        "runs": len(results),
        "method": extraction_method,
        "source_format": "mhtml" if is_mhtml_path(source_document_path) else "pdf",
        "source_document_path": str(source_document_path),
        "stored_original_path": str(stored_original_path) if stored_original_path else None,
    }
    if mhtml_tables:
        metadata["mhtml_table_count"] = mhtml_tables.table_count
    elif is_mhtml_path(source_document_path):
        metadata["processing_pdf_path"] = str(processing_pdf_path)
    result = save_import(
        bundle_dir=bundle_dir,
        pdf_path=processing_pdf_path,
        page_count=page_count,
        raw_text=raw_text,
        metadata=metadata,
        consensus=consensus,
        photo=photo,
        extraction_method=extraction_method,
        source_thread=source_thread,
        document_path=source_document_path if is_mhtml_path(source_document_path) else None,
        stored_document_path=stored_original_path,
        document_type="life_record_mhtml" if is_mhtml_path(source_document_path) else "school_life_record",
        sections=sections,
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
        "photo_display_path": _copy_photo_for_display(result.get("photo_paths") or []),
        "source_document_path": str(source_document_path),
        "stored_original_path": str(stored_original_path) if stored_original_path else None,
        "converted_pdf_path": None if mhtml_tables else (str(processing_pdf_path) if is_mhtml_path(source_document_path) else None),
        "mhtml_table_count": mhtml_tables.table_count if mhtml_tables else None,
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
    Lets the gateway auto-route any attached PDF/MHTML without the user naming a
    tool — and without misrouting non-생기부 documents (they return no)."""
    _validate_document_path(pdf_path)
    if is_mhtml_path(pdf_path):
        source_page_texts = extract_mhtml_text(pdf_path)
        source_text = "\n".join(source_page_texts)
        if _looks_like_life_record_text(source_text):
            return True
        if source_text.strip():
            return False
    else:
        extracted = extract_pdf(pdf_path)
        source_text = "\n".join(extracted.page_texts)
        if source_text.strip():
            return _looks_like_life_record_text(source_text)
    if resolver is None:
        with tempfile.TemporaryDirectory(prefix="miho_life_record_gate_") as tmp:
            gate_path = _normalize_to_pdf(pdf_path, Path(tmp))
            private_text = await asyncio.to_thread(
                read_private_first_page_text,
                gate_path,
            )
        return _looks_like_life_record_text(private_text)
    with tempfile.TemporaryDirectory(prefix="miho_life_record_gate_") as tmp:
        gate_path = _normalize_to_pdf(pdf_path, Path(tmp))
        images = [to_data_url(png) for png in render_page_images(gate_path, zoom=2.0, pages=[0])]
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
    verification = result.get("verification") or {}
    verified = verification.get("status") == "pass" and not verification.get("human_review_required")
    if verified:
        lines = [f"📄 {name} 생기부를 검증 통과 상태로 스레드 DB에 저장했습니다."]
    else:
        lines = [f"📄 {name} 생기부 원본을 스레드 DB에 보관했습니다. 구조화 결과는 검수 필요 상태입니다."]
    if result.get("photo_display_path"):
        lines.append(f"MEDIA:{result['photo_display_path']}")
    lines.append(
        f"- 성적 {counts.get('subject_grade_rows', 0)} · 세특 {counts.get('special_note_rows', 0)} · "
        f"출결 {counts.get('attendance_rows', 0)} · 수상 {counts.get('award_rows', 0)}"
    )
    if not verified:
        failed = verification.get("failed_rounds", 0)
        lines.append(f"- 검증 상태: {verification.get('status', 'needs_review')} · 실패 라운드 {failed}건")
    pending_grades = result.get("pending_grades") or []
    if pending_grades:
        lines.append(f"\n⚠️ 점수 검수 필요 {len(pending_grades)}건 (원본과 대조해 확정):")
        for g in pending_grades[:12]:
            sem = f"{g.get('semester')}학기" if g.get("semester") else ""
            rank = f" {g.get('rank_grade')}등급" if g.get("rank_grade") else ""
            lines.append(f"  · {g.get('grade')}학년{sem} {g.get('subject')} {g.get('raw_score') or '—'}{rank}")
        if len(pending_grades) > 12:
            lines.append(f"  · …외 {len(pending_grades) - 12}건")
        lines.append("→ life_record_review로 확인이 필요한 항목만 원장님께 안내해 주세요. 원장님 답변을 반영한 뒤 최종 확정할 수 있습니다.")
    promoted = result.get("promoted")
    if result.get("consensus_complete") and promoted and promoted.get("ok"):
        lines.append("- 전 항목 합의 완료 → 중앙 학생DB에 저장됨 (이후 life_record_lookup으로 조회 가능)")
    elif promoted and not promoted.get("ok"):
        lines.append(f"- 중앙 학생DB 승격 보류: {promoted.get('reason') or '검수/신원 확인 필요'}")
    if result.get("review_path"):
        lines.append(f"- (PC 상세 검수표·원본 페이지 포함: {result['review_path']})")
    return "\n".join(lines)


def _copy_photo_for_display(photo_paths: list[str]) -> str | None:
    """Copy the student photo into cache/media (a delivery-allowed root) so the
    Discord reply can attach it via MEDIA:. The bundle photo lives under the thread
    workspace, which isn't a delivery root."""
    if not photo_paths:
        return None
    src = Path(photo_paths[0])
    if not src.exists():
        return None
    try:
        from miho_constants import get_miho_dir

        dest_dir = get_miho_dir("cache/media", "media_cache") / "life_record_photos"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        return str(dest)
    except OSError:
        return None


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


def _normalize_to_pdf(document_path: Path, bundle_dir: Path, *, page_texts: list[str] | None = None) -> Path:
    if is_mhtml_path(document_path):
        converted_dir = bundle_dir / "converted"
        texts = page_texts if page_texts is not None else extract_mhtml_text(document_path)
        if has_text_layer(texts):
            return create_text_pdf(texts, converted_dir / f"{document_path.stem}_source_text.pdf")
        return convert_mhtml_to_pdf(document_path, converted_dir)
    return document_path


def _looks_like_life_record_text(text: str) -> bool:
    compact = "".join((text or "").split())
    if not compact:
        return False
    markers = ("학교생활기록부", "생활기록부", "학생부", "교과학습발달상황", "창의적 체험활동", "출결상황")
    return any(marker in compact for marker in markers)


def _extract_mhtml_tables(document_path: Path) -> Any | None:
    try:
        parsed = extract_neis_mhtml_tables(document_path)
    except (OSError, UnicodeError, ValueError) as exc:
        logger.warning("life_record: mhtml table extraction failed: %s", exc)
        return None
    identity = parsed.extraction.get("identity") or {}
    if not identity.get("name") or not parsed.extraction.get("grades"):
        return None
    return parsed


def _mhtml_model_pass_enabled() -> bool:
    return os.getenv("MIHO_LIFE_RECORD_MHTML_MODEL_PASS", "").strip().lower() in {"1", "true", "yes", "on"}


def _pdf_model_pass_enabled() -> bool:
    return os.getenv("MIHO_LIFE_RECORD_TEXT_MODEL_PASS", "").strip().lower() in {"1", "true", "yes", "on"}


def _store_original_document(bundle_dir: Path, document_path: Path) -> Path:
    source_dir = bundle_dir / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    suffix = preferred_document_suffix(document_path)
    try:
        from .utils import sha256_file

        digest = sha256_file(document_path)[:16]
    except Exception:
        digest = "source"
    stored = source_dir / f"{digest}_original{suffix}"
    if document_path.resolve() == stored.resolve():
        return stored
    shutil.copy2(document_path, stored)
    return stored


def _validate_document_path(document_path: Path) -> None:
    if not document_path.exists():
        raise ValueError(f"생기부 파일 경로를 찾을 수 없어: {document_path}")
    if not is_supported_document_path(document_path):
        raise ValueError("생기부는 PDF/MHTML/MHT 또는 해당 형식으로 확인되는 캐시 파일이어야 해.")


def _validate_pdf_path(pdf_path: Path) -> None:
    _validate_document_path(pdf_path)
