"""Rendering and physical PDF checks for hakjong reports."""

from __future__ import annotations

import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import jinja2

from . import hakjong_report_contract as _contract
from .brand_assets import academy_brand_logo_src
from .hakjong_report_contract import BRAND_TEXT
from .hakjong_stage_contract import normalize_student_stage
from .pdf_layout_contract import footer_layout_errors
from .report_fonts import report_font_css
from .student_card_capture import find_browser_executable


_KST = ZoneInfo("Asia/Seoul")
_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "hakjong_report_shell.html"
_BRAND_TEXT = BRAND_TEXT
_REPORT_PAGE_TARGET = 4
_COMPACT_STEPS = ("", "compact1", "compact2")


def render_html(content: dict[str, Any], body_class: str = "", student_stage: str = "") -> str:
    template_src = _TEMPLATE_PATH.read_text(encoding="utf-8")
    env = jinja2.Environment(
        loader=jinja2.BaseLoader(),
        autoescape=jinja2.select_autoescape(["html"]),
        undefined=jinja2.ChainableUndefined,
    )
    template = env.from_string(template_src)
    return template.render(
        font_css=report_font_css(),
        logo_src=academy_brand_logo_src() or "",
        brand_text=_BRAND_TEXT,
        report_date=datetime.now(_KST).date().isoformat(),
        data=content,
        body_class=body_class,
        student_stage=normalize_student_stage(student_stage),
    )


def render_pdf_fit(
    content: dict[str, Any], packaged_html: Path, packaged_pdf: Path, student_stage: str = ""
) -> str:
    html = render_html(content, student_stage=student_stage)
    page_target = expected_page_count(content)
    for body_class in _COMPACT_STEPS:
        html = render_html(content, body_class=body_class, student_stage=student_stage)
        packaged_html.write_text(html, encoding="utf-8")
        _chromium_print_to_pdf(packaged_html, packaged_pdf)
        pages = _contract._pdf_info(packaged_pdf).get("pages")
        if not pages or int(pages) <= page_target:
            break
    return html


def expected_page_count(content: dict[str, Any] | None) -> int:
    if not isinstance(content, dict):
        return _REPORT_PAGE_TARGET
    strategy = content.get("strategy_section")
    if not isinstance(strategy, dict):
        return _REPORT_PAGE_TARGET
    gap_plan = strategy.get("gap_plan")
    if not isinstance(gap_plan, dict):
        return _REPORT_PAGE_TARGET
    subjects = gap_plan.get("subjects")
    if not isinstance(subjects, list):
        return _REPORT_PAGE_TARGET
    return _REPORT_PAGE_TARGET + len(subjects)


def validate_pdf_physical(
    pdf_path: Path,
    *,
    content: dict[str, Any] | None = None,
    student_name: str,
    university_names: list[str],
    errors: list[str],
) -> None:
    size_mb = pdf_path.stat().st_size / 1_048_576
    if size_mb > 9.0:
        errors.append(
            f"PDF가 {size_mb:.1f}MB로 디스코드 첨부 한도(약 10MB)를 넘는다 — "
            "섹션/문단 분량을 줄여 9MB 아래로 다시 만들어라."
        )
    info = _contract._pdf_info(pdf_path)
    if info.get("error"):
        errors.append(f"PDF 정보를 읽을 수 없다: {info['error']}")
        return

    width = float(info.get("width") or 0)
    height = float(info.get("height") or 0)
    if width <= 0 or height <= 0:
        errors.append("PDF 페이지 크기를 파싱할 수 없다.")
    elif width > height:
        errors.append("PDF가 가로 방향이다. A4 세로여야 한다.")

    text_result = _contract._pdf_text(pdf_path)
    if text_result.get("error"):
        return
    body = str(text_result.get("text") or "")
    if content is not None:
        _contract.truncation_errors(content, body, errors)
    if _BRAND_TEXT not in body:
        errors.append(f"PDF 본문에 브랜드 텍스트가 없다: {_BRAND_TEXT}")
    if student_name and student_name not in body:
        errors.append(f"PDF 본문에 학생명이 없다: {student_name}")
    for uni in university_names:
        if uni and uni not in body:
            errors.append(f"PDF 본문에 대학명이 없다: {uni}")
    errors.extend(footer_layout_errors(pdf_path, expected_pages=expected_page_count(content)))


def university_names_from_content(content: dict[str, Any]) -> list[str]:
    university = content.get("university")
    if isinstance(university, dict):
        name = str(university.get("name") or "").strip()
        if name:
            return [name]
    return []


def safe_stem(*parts: str) -> str:
    raw = "_".join(part.strip() for part in parts if part and part.strip())
    clean = re.sub(r"[^\w가-힣.-]+", "_", raw, flags=re.UNICODE).strip("_.")
    return clean[:120] or "hakjong_report"


def unique_pair(html_path: Path, pdf_path: Path) -> tuple[Path, Path]:
    stem = html_path.stem
    parent = html_path.parent
    counter = 2
    candidate_html = html_path
    candidate_pdf = pdf_path
    while candidate_html.exists() or candidate_pdf.exists():
        candidate_html = parent / f"{stem}_{counter}.html"
        candidate_pdf = parent / f"{stem}_{counter}.pdf"
        counter += 1
    return candidate_html, candidate_pdf


def _chromium_print_to_pdf(html_path: Path, pdf_path: Path) -> None:
    browser = find_browser_executable()
    if browser is None:
        raise RuntimeError(
            "PDF 생성에 필요한 브라우저를 찾지 못했다. Chrome 또는 Edge 설치가 필요하다."
        )
    import shutil
    import sys

    playwright = shutil.which("playwright") or "/opt/homebrew/bin/playwright"
    if Path(playwright).exists():
        command = [
            playwright,
            "pdf",
            "--paper-format",
            "A4",
            "--timeout",
            "60000",
            html_path.as_uri(),
            str(pdf_path),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"PDF 생성이 시간 안에 끝나지 않았다: {exc}") from exc
        if result.returncode != 0 or not pdf_path.exists():
            detail = (result.stderr or result.stdout or "").strip()
            suffix = f" ({detail[:200]})" if detail else ""
            raise RuntimeError(f"Chromium PDF 생성 실패.{suffix}")
        return

    user_data_dir = tempfile.mkdtemp(prefix="miho-hakjong-chrome-")
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-background-networking",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={user_data_dir}",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        html_path.as_uri(),
    ]
    if sys.platform.startswith("linux"):
        command.insert(1, "--no-sandbox")

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"PDF 생성이 시간 안에 끝나지 않았다: {exc}") from exc

    if result.returncode != 0 or not pdf_path.exists():
        detail = (result.stderr or result.stdout or "").strip()
        suffix = f" ({detail[:200]})" if detail else ""
        raise RuntimeError(f"Chromium PDF 생성 실패.{suffix}")
