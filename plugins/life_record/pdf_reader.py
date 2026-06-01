"""PDF text and profile-photo extraction for school life records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import sha256_bytes


@dataclass(frozen=True)
class ExtractedPhoto:
    image_bytes: bytes
    ext: str
    source_page: int
    width: int
    height: int
    sha256: str


@dataclass(frozen=True)
class ExtractedPdf:
    page_texts: list[str]
    raw_text: str
    page_count: int
    metadata: dict[str, Any]
    photo: ExtractedPhoto | None


def _ensure_pdf_deps() -> None:
    try:
        from tools.lazy_deps import ensure
        ensure("tool.life_record", prompt=False)
    except Exception as exc:
        raise RuntimeError(f"생기부 PDF 처리 의존성을 준비하지 못했어: {exc}") from exc


def extract_pdf(pdf_path: Path) -> ExtractedPdf:
    _ensure_pdf_deps()
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF(fitz)를 불러오지 못했어.") from exc
    doc = fitz.open(str(pdf_path))
    try:
        page_texts = [page.get_text("text") or "" for page in doc]
        raw_text = "\n\n".join(f"--- PAGE {i + 1} ---\n{text}" for i, text in enumerate(page_texts))
        return ExtractedPdf(
            page_texts=page_texts,
            raw_text=raw_text,
            page_count=len(doc),
            metadata=dict(getattr(doc, "metadata", {}) or {}),
            photo=_extract_best_photo(doc),
        )
    finally:
        doc.close()


def _extract_best_photo(doc: Any) -> ExtractedPhoto | None:
    candidates: list[tuple[int, int, int, int, str, bytes]] = []
    seen: set[int] = set()
    for page_index, page in enumerate(doc):
        for image in page.get_images(full=True):
            xref = int(image[0])
            if xref in seen:
                continue
            seen.add(xref)
            pix = doc.extract_image(xref)
            image_bytes = pix.get("image") or b""
            if not image_bytes:
                continue
            width = int(pix.get("width") or 0)
            height = int(pix.get("height") or 0)
            score = _photo_score(page_index, width, height)
            if score > 0:
                candidates.append((score, page_index + 1, width, height, pix.get("ext") or "png", image_bytes))
    if not candidates:
        return None
    score, page, width, height, ext, image_bytes = sorted(candidates, reverse=True)[0]
    return ExtractedPhoto(
        image_bytes=image_bytes,
        ext=str(ext).lower().lstrip(".") or "png",
        source_page=page,
        width=width,
        height=height,
        sha256=sha256_bytes(image_bytes),
    )


def _photo_score(page_index: int, width: int, height: int) -> int:
    score = 0
    if page_index == 0:
        score += 10
    if height > width:
        score += 5
    if width >= 120 and height >= 160:
        score += 5
    if width * height > 30_000:
        score += 2
    return score


def extract_markdown(pdf_path: Path) -> str | None:
    """Convert a text-layer PDF to markdown via pymupdf4llm so tables/columns keep
    their structure (the LLM has far less to reconstruct than from raw get_text).
    Returns None when the dep is unavailable — caller falls back to plain page_texts,
    so this is a pure accuracy boost with no hard dependency. Mirrors miho's
    ocr-and-documents skill (pymupdf4llm --markdown)."""
    try:
        import pymupdf4llm
    except ImportError:
        return None
    try:
        text = pymupdf4llm.to_markdown(str(pdf_path), show_progress=False)
        return text if text and text.strip() else None
    except Exception:
        return None


def render_page_images(pdf_path: Path, *, zoom: float = 3.0, pages: list[int] | None = None) -> list[bytes]:
    """Render PDF pages to PNG bytes for vision extraction.

    zoom 3.0 ≈ 216 DPI — enough detail that the model reads small 주민번호/학교명
    glyphs (PoC showed zoom 2.5 caused 1-char mis-reads). ``pages`` (0-based) limits
    rendering to a subset when only specific pages are needed.
    """
    _ensure_pdf_deps()
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF(fitz)를 불러오지 못했어.") from exc
    doc = fitz.open(str(pdf_path))
    try:
        matrix = fitz.Matrix(zoom, zoom)
        want = set(pages) if pages is not None else None
        out: list[bytes] = []
        for index, page in enumerate(doc):
            if want is not None and index not in want:
                continue
            out.append(page.get_pixmap(matrix=matrix).tobytes("png"))
        return out
    finally:
        doc.close()
