"""PDF/MHTML text and profile-photo extraction for school life records."""

from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
import html
from pathlib import Path
import re
import subprocess
from typing import Any

from .utils import sha256_bytes

_PDF_SUFFIXES = {".pdf"}
_MHTML_SUFFIXES = {".mhtml", ".mht"}
_SNIFF_BYTES = 65536


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


def is_pdf_path(path: Path) -> bool:
    return path.suffix.lower() in _PDF_SUFFIXES or _read_head(path, 8).startswith(b"%PDF-")


def is_mhtml_path(path: Path) -> bool:
    return path.suffix.lower() in _MHTML_SUFFIXES or _looks_like_mhtml_bytes(_read_head(path))


def is_supported_document_path(path: Path) -> bool:
    return path.exists() and (is_pdf_path(path) or is_mhtml_path(path))


def preferred_document_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _PDF_SUFFIXES | _MHTML_SUFFIXES:
        return suffix
    if is_mhtml_path(path):
        return ".mhtml"
    if is_pdf_path(path):
        return ".pdf"
    return suffix or ".pdf"


def _read_head(path: Path, limit: int = _SNIFF_BYTES) -> bytes:
    try:
        with path.open("rb") as handle:
            return handle.read(limit)
    except OSError:
        return b""


def _looks_like_mhtml_bytes(data: bytes) -> bool:
    if not data:
        return False
    lowered = data.lower()
    header = lowered[:4096]
    has_mime_header = b"mime-version:" in header
    has_content_type = b"content-type:" in header
    has_html_or_archive_hint = b"<html" in lowered or b"content-location:" in lowered or b"boundary=" in header
    return has_mime_header and has_content_type and has_html_or_archive_hint


def extract_mhtml_text(mhtml_path: Path) -> list[str]:
    """Extract human-readable text directly from a Chrome MHTML/MHT file.

    MHTML saved from NEIS+ usually contains the full record as HTML/plain text.
    Reading that source is much faster and more reliable than first asking Chrome
    to print it to PDF, then reading the generated PDF text layer. Keep this as a
    best-effort helper: if the archive is malformed, callers can still fall back
    to PDF rendering/vision.
    """
    data = mhtml_path.read_bytes()
    texts: list[str] = []
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
        parts = message.walk() if message.is_multipart() else [message]
        for part in parts:
            content_type = (part.get_content_type() or "").lower()
            if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
                continue
            payload = _decode_mime_part_text(part)
            cleaned = _html_to_text(payload) if "html" in content_type or "xhtml" in content_type else _clean_text(payload)
            if cleaned:
                texts.append(cleaned)
    except Exception:
        # Some browsers export slightly non-compliant MHTML. Fall back to scanning
        # the raw bytes as text; this is still often enough for the 생기부 marker
        # and for model-based restructuring.
        for encoding in ("utf-8", "cp949", "euc-kr"):
            try:
                raw = data.decode(encoding)
                break
            except UnicodeDecodeError:
                raw = ""
        cleaned = _html_to_text(raw) if "<html" in raw.lower() else _clean_text(raw)
        if cleaned:
            texts.append(cleaned)
    return _dedupe_texts(texts)


def convert_mhtml_to_pdf(mhtml_path: Path, output_dir: Path, *, timeout: int = 20) -> Path:
    """Render a Chrome-saved MHTML/MHT document to PDF for the existing pipeline.

    NEIS+ on macOS often saves student records as Web Archive/MHTML when regular
    PDF export is awkward. PyMuPDF cannot open MHTML directly, so we normalize it
    into a PDF first and then reuse the exact same text/vision/consensus path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"{mhtml_path.stem}_from_mhtml.pdf"
    chrome = _chrome_executable()
    command = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--print-to-pdf={pdf_path}",
        mhtml_path.resolve().as_uri(),
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except OSError as exc:
        raise RuntimeError(f"MHTML을 PDF로 변환할 Chrome을 실행하지 못했어: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("MHTML을 PDF로 변환하는 시간이 너무 오래 걸렸어.") from exc
    if completed.returncode != 0 or not pdf_path.exists() or pdf_path.stat().st_size == 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:500]
        raise RuntimeError(f"MHTML을 PDF로 변환하지 못했어. {detail}".strip())
    return pdf_path


def create_text_pdf(page_texts: list[str], output_path: Path) -> Path:
    """Create a lightweight review/storage PDF from extracted text.

    Used when Chrome cannot print MHTML quickly. It keeps the ingest/verifier path
    intact without letting a flaky browser render block the source-text fast path.
    """
    _ensure_pdf_deps()
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF(fitz)를 불러오지 못했어.") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    try:
        pages = page_texts or [""]
        for text in pages:
            page = doc.new_page(width=595, height=842)  # A4-ish
            rect = fitz.Rect(36, 36, 559, 806)
            page.insert_textbox(rect, text[:6000], fontsize=8, fontname="helv", align=0)
        doc.save(str(output_path))
    finally:
        doc.close()
    return output_path


def _decode_mime_part_text(part: Any) -> str:
    """Decode a text MIME part without mojibake.

    Python's EmailMessage.get_content() can sometimes return replacement-heavy
    text for Chrome-saved NEIS MHTML even though get_payload(decode=True) is
    clean quoted-printable UTF-8. Prefer the decoded bytes when available.
    """
    charset = part.get_content_charset() or "utf-8"
    decoded = part.get_payload(decode=True)
    candidates: list[str] = []
    if decoded:
        for enc in (charset, "utf-8", "cp949", "euc-kr"):
            try:
                candidates.append(decoded.decode(enc, errors="replace"))
            except LookupError:
                continue
    try:
        content = part.get_content()
        if isinstance(content, (bytes, bytearray)):
            candidates.append(bytes(content).decode(charset, errors="replace"))
        else:
            candidates.append(str(content))
    except Exception:
        pass
    if not candidates:
        return ""
    return min(candidates, key=lambda text: text.count("�"))


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", value or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|table|li|h[1-6])>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return _clean_text(html.unescape(text))


def _clean_text(value: str) -> str:
    text = html.unescape(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t\x0b\x0c ]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _dedupe_texts(texts: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for text in texts:
        key = re.sub(r"\s+", " ", text)[:500]
        if len(text) < 5 or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _chrome_executable() -> str:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "google-chrome",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
    ]
    for candidate in candidates:
        if candidate.startswith("/"):
            if Path(candidate).exists():
                return candidate
            continue
        try:
            probe = subprocess.run(["/usr/bin/env", "which", candidate], check=False, capture_output=True, text=True, timeout=5)
        except OSError:
            continue
        if probe.returncode == 0 and probe.stdout.strip():
            return candidate
    raise RuntimeError("MHTML 변환용 Chrome/Chromium/Edge를 찾지 못했어.")


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


def crop_id_photo(pdf_path: Path, bbox_ratio: dict[str, float], *, zoom: float = 3.0) -> ExtractedPhoto | None:
    """Crop the first page to the given 0~1 bbox (from vision) — used to pull just
    the ID photo out of a scanned PDF whose page is a single image."""
    _ensure_pdf_deps()
    try:
        import fitz
    except ImportError:
        return None
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[0]
        r = page.rect
        clip = fitz.Rect(bbox_ratio["x0"] * r.width, bbox_ratio["y0"] * r.height, bbox_ratio["x1"] * r.width, bbox_ratio["y1"] * r.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
        png = pix.tobytes("png")
        return ExtractedPhoto(
            image_bytes=png, ext="png", source_page=1,
            width=pix.width, height=pix.height, sha256=sha256_bytes(png),
        )
    except Exception:
        return None
    finally:
        doc.close()


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
