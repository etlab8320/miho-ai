"""Render PDF, image, URL, and text-like documents into page evidence images."""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
import html
import json
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .storage import document_dir, document_id_for, sha256_bytes


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
TEXT_SUFFIXES = {".html", ".htm", ".mhtml", ".mht", ".txt"}
PDF_MAGIC = b"%PDF-"
MAX_RENDER_PAGES = 200
MAX_PAGE_NUMBER_DIGITS = 6


def capabilities() -> dict[str, Any]:
    return {
        "pdf_render": True,
        "pdf_render_backend_available": _module_available("fitz"),
        "pdf_render_install": "lazy PyMuPDF==1.26.6",
        "pdf_page_range": True,
        "image_render": _module_available("PIL.Image"),
        "html_mhtml_text_fallback": True,
        "url_fetch": True,
        "browser_pixel_render": False,
        "browser_pixel_render_note": "Playwright/Chromium 연결 전에는 HTML/MHTML은 text_fallback 이미지로 저장합니다.",
    }


def render_source(source: str, *, max_pages: int = 30, zoom: float = 2.5, page_range: str | None = None) -> dict[str, Any]:
    if not str(source or "").strip():
        raise ValueError("문서 경로 또는 URL이 필요합니다.")
    with TemporaryDirectory(prefix="miho_pixel_doc_") as temp:
        local_source, fetched_meta = _resolve_source(source, Path(temp))
        raw = local_source.read_bytes()
        source_sha256 = sha256_bytes(raw)
        render_key = _render_key(source_sha256, max_pages=max_pages, zoom=zoom, page_range=page_range)
        document_id = document_id_for(render_key)
        out_dir = document_dir(document_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        source_copy = out_dir / f"source{_preferred_suffix(local_source, raw)}"
        if not source_copy.exists():
            source_copy.write_bytes(raw)
        kind = _detect_kind(local_source, raw)
        if kind == "pdf":
            pages, meta = _render_pdf(local_source, out_dir, max_pages=max_pages, zoom=zoom, page_range=page_range)
        elif kind == "image":
            pages, meta = _render_image(local_source, out_dir, page_range=page_range)
        else:
            pages, meta = _render_text_fallback(local_source, out_dir, page_range=page_range)
        meta.update(fetched_meta)
        return {
            "document_id": document_id,
            "document_dir": str(out_dir),
            "source_id": document_id_for(raw, prefix="pde_source"),
            "source_path": str(source_copy),
            "source_sha256": source_sha256,
            "source_kind": kind,
            "source_label": str(source),
            "render": meta,
            "pages": pages,
        }


def _resolve_source(source: str, temp_dir: Path) -> tuple[Path, dict[str, Any]]:
    text = str(source).strip()
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"}:
        return _fetch_url(text, temp_dir)
    path = Path(text).expanduser()
    if not path.exists():
        raise ValueError("문서 경로를 찾을 수 없습니다. 첨부 파일의 로컬 경로나 URL을 다시 확인해 주세요.")
    if not path.is_file():
        raise ValueError("문서 경로가 파일이 아닙니다.")
    return path, {"source_origin": "local_file"}


def _fetch_url(url: str, temp_dir: Path) -> tuple[Path, dict[str, Any]]:
    req = Request(url, headers={"User-Agent": "MihoPixelDocumentEvidence/0.1"})
    with urlopen(req, timeout=20) as response:  # noqa: S310 - user supplied URL is expected input for this tool
        data = response.read(25_000_000)
        content_type = str(response.headers.get("content-type") or "").split(";")[0].lower()
    suffix = _suffix_from_content_type(content_type) or Path(urlparse(url).path).suffix or ".html"
    out = temp_dir / f"fetched{suffix}"
    out.write_bytes(data)
    return out, {"source_origin": "url", "source_url": url, "content_type": content_type}


def _detect_kind(path: Path, data: bytes) -> str:
    suffix = path.suffix.lower()
    if data.startswith(PDF_MAGIC) or suffix == ".pdf":
        return "pdf"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    return "text_fallback"


def _preferred_suffix(path: Path, data: bytes) -> str:
    if data.startswith(PDF_MAGIC):
        return ".pdf"
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES | TEXT_SUFFIXES | {".pdf"}:
        return suffix
    return ".bin"


def _render_pdf(
    path: Path,
    out_dir: Path,
    *,
    max_pages: int,
    zoom: float,
    page_range: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _ensure_pymupdf()
    import fitz  # type: ignore[import-not-found]

    pages: list[dict[str, Any]] = []
    doc = fitz.open(str(path))
    try:
        matrix = fitz.Matrix(zoom, zoom)
        page_count = len(doc)
        selected_pages, truncated, range_label = _select_page_numbers(page_count, page_range, max_pages=max_pages)
        for page_number in selected_pages:
            page = doc.load_page(page_number - 1)
            image_path = out_dir / f"page_{page_number:04d}.png"
            text = page.get_text("text") or ""
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            pix.save(str(image_path))
            pages.append(_page_payload(page_number, image_path, pix.width, pix.height, text, "pdf_text_layer", "pdf_page"))
    finally:
        doc.close()
    return pages, {
        "status": "ready",
        "mode": "pdf_page",
        "page_count": page_count,
        "rendered_pages": len(pages),
        "selected_pages": [page["page_number"] for page in pages],
        "page_range": range_label,
        "truncated": truncated,
    }


def _render_image(path: Path, out_dir: Path, *, page_range: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected_pages, truncated, range_label = _select_page_numbers(1, page_range, max_pages=1)
    image_path = out_dir / "page_0001.png"
    width, height = _normalize_image(path, image_path)
    page = _page_payload(selected_pages[0], image_path, width, height, "", "pending_ocr", "image_page")
    return [page], {
        "status": "ready",
        "mode": "image_page",
        "page_count": 1,
        "rendered_pages": 1,
        "selected_pages": selected_pages,
        "page_range": range_label,
        "truncated": truncated,
    }


def _render_text_fallback(path: Path, out_dir: Path, *, page_range: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected_pages, truncated, range_label = _select_page_numbers(1, page_range, max_pages=1)
    text = _extract_text_fallback(path.read_bytes())
    image_path = out_dir / "page_0001.png"
    width, height = _text_to_image(text or path.name, image_path)
    page = _page_payload(selected_pages[0], image_path, width, height, text, "text_fallback", "text_fallback")
    return [page], {
        "status": "ready",
        "mode": "text_fallback",
        "page_count": 1,
        "rendered_pages": 1,
        "selected_pages": selected_pages,
        "page_range": range_label,
        "truncated": truncated,
        "confidence": "reduced_layout",
        "warning_ko": "브라우저 렌더러가 없어 원본 레이아웃 대신 텍스트 fallback 이미지를 저장했습니다.",
    }


def _select_page_numbers(page_count: int, page_range: str | None, *, max_pages: int) -> tuple[list[int], bool, str]:
    range_label = str(page_range or "").strip()
    render_limit = _render_limit(max_pages)
    if range_label:
        selected = _parse_page_range(range_label, page_count=page_count, render_limit=render_limit)
        truncated = False
    else:
        selected = list(range(1, min(page_count, render_limit) + 1))
        truncated = page_count > len(selected)
    if not selected:
        raise ValueError("선택한 페이지 범위에 해당하는 페이지가 없습니다.")
    return selected, truncated, range_label


def _parse_page_range(value: str, *, page_count: int, render_limit: int) -> list[int]:
    normalized = value.replace("~", "-").replace("–", "-").replace("—", "-")
    numbers: set[int] = set()
    for chunk in normalized.split(","):
        part = chunk.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = [item.strip() for item in part.split("-", 1)]
            start, end = _parse_page_number(start_text), _parse_page_number(end_text)
            if end < start:
                raise ValueError("페이지 범위는 시작 쪽이 끝 쪽보다 클 수 없습니다.")
            _ensure_range_fits_document(start, end, page_count)
            if end - start + 1 > render_limit:
                raise ValueError(f"요청한 페이지 범위가 최대 렌더 페이지 수({render_limit}쪽)를 넘습니다.")
            for number in range(start, end + 1):
                numbers.add(number)
                _ensure_selection_limit(numbers, render_limit)
        else:
            number = _parse_page_number(part)
            _ensure_range_fits_document(number, number, page_count)
            numbers.add(number)
            _ensure_selection_limit(numbers, render_limit)
    if not numbers:
        raise ValueError("페이지 범위가 필요합니다. 예: 2 또는 3-5")
    return sorted(numbers)


def _parse_page_number(value: str) -> int:
    if not value.isdigit():
        raise ValueError("페이지 범위는 숫자와 쉼표, 하이픈만 사용할 수 있습니다. 예: 1,3-5")
    if len(value) > MAX_PAGE_NUMBER_DIGITS:
        raise ValueError(f"페이지 번호는 {MAX_PAGE_NUMBER_DIGITS}자리 이하로 지정해 주세요.")
    number = int(value)
    if number < 1:
        raise ValueError("페이지 번호는 1쪽부터 지정해 주세요.")
    return number


def _ensure_range_fits_document(start: int, end: int, page_count: int) -> None:
    if start > page_count or end > page_count:
        overflow = start if start > page_count else end
        raise ValueError(f"선택한 페이지 범위가 문서 페이지 수({page_count}쪽)를 벗어났습니다: {overflow}쪽")


def _ensure_selection_limit(numbers: set[int], render_limit: int) -> None:
    if len(numbers) > render_limit:
        raise ValueError(f"요청한 페이지 범위가 최대 렌더 페이지 수({render_limit}쪽)를 넘습니다.")


def _render_limit(max_pages: int) -> int:
    try:
        parsed = int(max_pages)
    except (TypeError, ValueError):
        parsed = 1
    return max(1, min(parsed, MAX_RENDER_PAGES))


def _render_key(source_sha256: str, *, max_pages: int, zoom: float, page_range: str | None) -> bytes:
    payload = {
        "source_sha256": source_sha256,
        "max_pages": _render_limit(max_pages),
        "page_range": str(page_range or "").strip(),
        "zoom": round(float(zoom), 4),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _page_payload(
    number: int,
    image_path: Path,
    width: int,
    height: int,
    text: str,
    text_source: str,
    render_mode: str,
) -> dict[str, Any]:
    image_bytes = image_path.read_bytes()
    return {
        "page_number": number,
        "page_image_path": str(image_path),
        "width": width,
        "height": height,
        "image_sha256": sha256_bytes(image_bytes),
        "text": text.strip(),
        "text_source": text_source,
        "render_mode": render_mode,
        "ocr_spans": [],
    }


def _ensure_pymupdf() -> None:
    try:
        from tools.lazy_deps import ensure

        ensure("tool.pixel_documents_pdf", prompt=False)
    except Exception:
        pass
    try:
        import fitz  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("PDF 렌더링 의존성(PyMuPDF)을 준비하지 못했습니다.") from exc


def _normalize_image(path: Path, output: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            converted = image.convert("RGB")
            converted.save(output, format="PNG")
            return converted.width, converted.height
    except Exception:
        shutil.copyfile(path, output)
        return 0, 0


def _text_to_image(text: str, output: Path) -> tuple[int, int]:
    from PIL import Image, ImageDraw, ImageFont

    width = 1400
    margin = 48
    font = _font(size=28)
    lines = _wrap_text(text, max_chars=52)
    line_height = 40
    height = max(700, margin * 2 + line_height * max(1, len(lines)))
    image = Image.new("RGB", (width, min(height, 5000)), "white")
    draw = ImageDraw.Draw(image)
    y = margin
    for line in lines[:120]:
        draw.text((margin, y), line, fill=(24, 28, 35), font=font)
        y += line_height
    image.save(output, format="PNG")
    return image.width, image.height


def _font(size: int) -> Any:
    from PIL import ImageFont

    for candidate in (
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, *, max_chars: int) -> list[str]:
    words = re.split(r"(\s+)", re.sub(r"\s+", " ", text or "").strip())
    lines: list[str] = []
    current = ""
    for token in words:
        if len(current) + len(token) > max_chars and current:
            lines.append(current.strip())
            current = token
        else:
            current += token
    if current.strip():
        lines.append(current.strip())
    return lines or [""]


def _extract_text_fallback(data: bytes) -> str:
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
        if message.is_multipart():
            chunks = []
            for part in message.walk():
                if part.get_content_type() in {"text/html", "text/plain", "application/xhtml+xml"}:
                    chunks.append(_decode_part(part))
            if chunks:
                return _clean_html("\n".join(chunks))
    except Exception:
        pass
    raw = _decode_bytes(data)
    return _clean_html(raw) if "<" in raw and ">" in raw else _clean_text(raw)


def _decode_part(part: Any) -> str:
    charset = part.get_content_charset() or "utf-8"
    payload = part.get_payload(decode=True)
    if payload:
        return _decode_bytes(payload, preferred=charset)
    try:
        return str(part.get_content())
    except Exception:
        return ""


def _decode_bytes(data: bytes, *, preferred: str = "utf-8") -> str:
    for enc in (preferred, "utf-8", "cp949", "euc-kr"):
        try:
            return data.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _clean_html(value: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", value or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|table|li|h[1-6]|td|th)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return _clean_text(html.unescape(text))


def _clean_text(value: str) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t\x0b\x0c ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _suffix_from_content_type(content_type: str) -> str:
    return {
        "application/pdf": ".pdf",
        "text/html": ".html",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(content_type, "")


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False
