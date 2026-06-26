#!/usr/bin/env python3
"""Render a new HTML-first Korean PDF and produce QA artifacts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


FORBIDDEN_BYTES = (
    b"Miho",
    b"OpenAI",
    b"ChatGPT",
    b"ReportLab",
    b"/Author",
    b"/Creator",
    b"/Producer",
    b"/Title",
)
FORBIDDEN_TEXT = ("Miho", "미호", "OpenAI", "ChatGPT", "ReportLab", "AI가")


def main() -> int:
    args = _parse_args()
    html_path = Path(args.html).expanduser().resolve(strict=True)
    pdf_path = Path(args.pdf).expanduser().resolve()
    preview_dir = _preview_dir(args.preview_dir, pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    engine = _choose_engine(args.engine)
    engine, render_warning = _render_pdf(html_path, pdf_path, engine=engine, timeout=args.timeout)

    _scrub_pdf(pdf_path)
    page_paths = _render_pages(pdf_path, preview_dir, zoom=args.zoom)
    contact_sheet = _make_contact_sheet(page_paths, preview_dir / "contact_sheet.png")
    facts = _inspect_pdf(pdf_path)
    facts.update(
        {
            "ok": _basic_ok(facts, page_paths, contact_sheet),
            "engine": engine,
            "render_warning": render_warning,
            "html_path": str(html_path),
            "pdf_path": str(pdf_path),
            "preview_dir": str(preview_dir),
            "page_images": [str(path) for path in page_paths],
            "contact_sheet": str(contact_sheet) if contact_sheet else "",
            "visual_review_required": True,
            "review_prompt": _review_prompt(),
        }
    )
    print(json.dumps(facts, ensure_ascii=False, indent=2))
    return 0 if facts["ok"] else 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render HTML to PDF, scrub metadata, and build PDF QA previews."
    )
    parser.add_argument("--html", required=True, help="Source HTML path.")
    parser.add_argument("--pdf", required=True, help="Final PDF output path.")
    parser.add_argument(
        "--engine",
        choices=("auto", "chrome", "playwright", "vivliostyle"),
        default="auto",
        help="Renderer. auto uses Playwright when available, then Chrome unless MIHO_PDF_ENGINE is set.",
    )
    parser.add_argument("--preview-dir", default="", help="Directory for page PNGs.")
    parser.add_argument("--timeout", type=int, default=90, help="Render timeout seconds.")
    parser.add_argument("--zoom", type=float, default=1.6, help="PDF rasterization zoom.")
    return parser.parse_args()


def _choose_engine(engine: str) -> str:
    if engine in {"chrome", "playwright", "vivliostyle"}:
        return engine
    configured = os.environ.get("MIHO_PDF_ENGINE", "").strip()
    if configured in {"chrome", "playwright", "vivliostyle"}:
        return configured
    if os.environ.get("VIVLIOSTYLE_CMD", "").strip() or shutil.which("vivliostyle"):
        return "vivliostyle"
    if shutil.which("playwright"):
        return "playwright"
    return "chrome"


def _render_pdf(html_path: Path, pdf_path: Path, *, engine: str, timeout: int) -> tuple[str, str]:
    if engine == "vivliostyle":
        _render_with_vivliostyle(html_path, pdf_path, timeout=timeout)
        return "vivliostyle", ""
    if engine == "playwright":
        _render_with_playwright(html_path, pdf_path, timeout=timeout)
        return "playwright", ""
    try:
        _render_with_chrome(html_path, pdf_path, timeout=timeout)
        return "chrome", ""
    except RuntimeError as exc:
        _render_with_playwright(html_path, pdf_path, timeout=timeout)
        return "playwright", f"chrome renderer failed; recovered with Playwright: {exc}"


def _render_with_chrome(html_path: Path, pdf_path: Path, *, timeout: int) -> None:
    chrome = _find_chrome()
    if not chrome:
        raise RuntimeError("Chrome executable was not found for HTML-to-PDF rendering.")
    with tempfile.TemporaryDirectory(prefix="miho-pdf-chrome-") as user_data_dir:
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--allow-file-access-from-files",
            "--no-pdf-header-footer",
            f"--user-data-dir={user_data_dir}",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ]
        _run(cmd, timeout=timeout)


def _render_with_vivliostyle(html_path: Path, pdf_path: Path, *, timeout: int) -> None:
    command = os.environ.get("VIVLIOSTYLE_CMD", "").strip()
    if command:
        cmd = [command, "build", str(html_path), "-o", str(pdf_path)]
    elif vivliostyle := shutil.which("vivliostyle"):
        cmd = [vivliostyle, "build", str(html_path), "-o", str(pdf_path)]
    else:
        npx = shutil.which("npx")
        if not npx:
            raise RuntimeError("npx was not found for @vivliostyle/cli rendering.")
        cmd = [npx, "--yes", "@vivliostyle/cli", "build", str(html_path), "-o", str(pdf_path)]
    _run(cmd, timeout=timeout)


def _render_with_playwright(html_path: Path, pdf_path: Path, *, timeout: int) -> None:
    playwright = shutil.which("playwright")
    if not playwright:
        raise RuntimeError("playwright CLI was not found for HTML-to-PDF rendering.")
    cmd = [playwright, "pdf", html_path.as_uri(), str(pdf_path)]
    _run(cmd, timeout=timeout)


def _run(cmd: list[str], *, timeout: int) -> None:
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"PDF renderer failed with exit code {proc.returncode}: {detail[:1000]}")


def _find_chrome() -> str:
    candidates = [
        os.environ.get("CHROME_PATH", ""),
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return ""


def _scrub_pdf(pdf_path: Path) -> None:
    import fitz  # type: ignore[import-untyped]

    tmp_path = pdf_path.with_suffix(".clean.pdf")
    with fitz.open(str(pdf_path)) as doc:
        doc.set_metadata(
            {
                "title": "",
                "author": "",
                "subject": "",
                "keywords": "",
                "creator": "",
                "producer": "",
                "creationDate": "",
                "modDate": "",
                "trapped": "",
            }
        )
        try:
            doc.del_xml_metadata()
        except (AttributeError, RuntimeError, ValueError):
            pass
        try:
            doc.xref_set_key(-1, "Info", "null")
        except (RuntimeError, ValueError):
            pass
        doc.save(str(tmp_path), garbage=4, deflate=True, clean=True)
    tmp_path.replace(pdf_path)


def _render_pages(pdf_path: Path, preview_dir: Path, *, zoom: float) -> list[Path]:
    import fitz  # type: ignore[import-untyped]

    for old in preview_dir.glob("page_*.png"):
        old.unlink()
    page_paths: list[Path] = []
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(str(pdf_path)) as doc:
        for index, page in enumerate(doc, 1):
            page_path = preview_dir / f"page_{index:02d}.png"
            page.get_pixmap(matrix=matrix, alpha=False).save(str(page_path))
            page_paths.append(page_path)
    return page_paths


def _make_contact_sheet(page_paths: list[Path], output_path: Path) -> Path | None:
    if not page_paths:
        return None
    from PIL import Image, ImageDraw

    thumbs: list[Image.Image] = []
    for index, path in enumerate(page_paths, 1):
        image = Image.open(path).convert("RGB")
        image.thumbnail((360, 510))
        tile = Image.new("RGB", (390, 550), "white")
        tile.paste(image, ((390 - image.width) // 2, 28))
        ImageDraw.Draw(tile).text((12, 8), f"PAGE {index}", fill=(70, 70, 70))
        thumbs.append(tile)
    columns = min(3, len(thumbs))
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 390, rows * 550), (238, 242, 246))
    for index, tile in enumerate(thumbs):
        sheet.paste(tile, ((index % columns) * 390, (index // columns) * 550))
    sheet.save(output_path)
    return output_path


def _inspect_pdf(pdf_path: Path) -> dict[str, Any]:
    import fitz  # type: ignore[import-untyped]

    with fitz.open(str(pdf_path)) as doc:
        text = "\n".join(page.get_text("text") for page in doc)
        metadata = dict(doc.metadata or {})
        page_count = doc.page_count
        layout_errors = _layout_errors(doc)
    blob = pdf_path.read_bytes()
    return {
        "page_count": page_count,
        "metadata": metadata,
        "text_length": len(text),
        "forbidden_text_hits": [term for term in FORBIDDEN_TEXT if term in text],
        "forbidden_byte_hits": [
            term.decode("latin1") for term in FORBIDDEN_BYTES if blob.find(term) >= 0
        ],
        "layout_errors": layout_errors,
        "size_bytes": pdf_path.stat().st_size,
    }


def _basic_ok(facts: dict[str, Any], page_paths: list[Path], contact_sheet: Path | None) -> bool:
    return (
        bool(page_paths)
        and bool(contact_sheet)
        and facts.get("page_count", 0) > 0
        and facts.get("text_length", 0) > 0
        and not facts.get("layout_errors")
        and not facts.get("forbidden_text_hits")
        and not facts.get("forbidden_byte_hits")
    )


def _layout_errors(doc: Any) -> list[str]:
    errors: list[str] = []
    for page_index, page in enumerate(doc, start=1):
        page_rect = page.rect
        blocks = [
            block
            for block in page.get_text("blocks")
            if len(block) >= 5 and str(block[4] or "").strip()
        ]
        if not blocks:
            errors.append(f"{page_index}페이지가 빈 페이지로 렌더됐다.")
            continue
        footer_bottom_found = False
        footer_top_orphan = False
        for block in blocks:
            x0, y0, x1, y1 = map(float, block[:4])
            text = str(block[4] or "")
            if x0 < -1 or y0 < -1 or x1 > page_rect.width + 1 or y1 > page_rect.height + 1:
                errors.append(f"{page_index}페이지 텍스트 블록이 페이지 밖으로 밀렸다.")
            if _looks_like_footer(text):
                footer_bottom_found = footer_bottom_found or y0 >= page_rect.height - 70
                footer_top_orphan = footer_top_orphan or y0 <= 90
                if y1 > page_rect.height - 2:
                    errors.append(f"{page_index}페이지 footer가 하단 밖으로 잘렸다.")
        if footer_top_orphan and not footer_bottom_found:
            errors.append(f"{page_index}페이지 footer가 다음 페이지 상단으로 밀렸다.")
    return errors


def _looks_like_footer(text: str) -> bool:
    normalized = " ".join(str(text or "").split())
    if not normalized or len(normalized) > 160:
        return False
    markers = ("맥스체대입시", "확인용", "report", "리포트", "상담자료")
    return any(marker.casefold() in normalized.casefold() for marker in markers)


def _preview_dir(raw: str, pdf_path: Path) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    return pdf_path.parent / f"{pdf_path.stem}_preview"


def _review_prompt() -> str:
    return (
        "이 PDF contact sheet를 최종 납품 전 디자인 reviewer로 검수해줘. "
        "한국어 줄바꿈, 좌우 정렬, 페이지 균형, 푸터 가독성, 겹침/잘림, 빈 공간, "
        "반복 박스 남발, coordinate-drawn처럼 보이는지, 실제 상담/제안 자료로 보낼 수 있는지 판정해. "
        "문제가 있으면 fail과 수정 지시를, 통과하면 pass와 확인 항목을 반환해."
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
