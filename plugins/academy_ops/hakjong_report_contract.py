"""Validation contract for student hakjong report delivery."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .hakjong_stage_contract import has_early_context_evidence, validate_stage_contract


BRAND_TEXT = "맥스체대입시 일산교육원"
REPORT_TITLE = "학생부종합 지원전략 리포트"
AUDIENCE_LABEL = "학생·학부모 확인용"

REQUIRED_HTML_PATTERNS = {
    "identity.maxReport": r'<body[^>]*class=["\'][^"\']*\bmaxReport\b',
    "identity.reportIdentity": r'class=["\'][^"\']*\breportIdentity\b',
    "identity.sectionDeck": r'class=["\'][^"\']*\bsectionDeck\b',
    "template.brandline": r'class=["\'][^"\']*\bbrandline\b',
    "template.coverCenter": r'class=["\'][^"\']*\bcoverCenter\b',
    "template.heroCard": r'class=["\'][^"\']*\bheroCard\b',
    "template.coverMetrics": r'class=["\'][^"\']*\bcoverMetrics\b',
    "template.topbar": r'class=["\'][^"\']*\btopbar\b',
    "template.footer": r'class=["\'][^"\']*\bfooter\b',
    "css.brandline": r"\.brandline",
    "css.coverCenter": r"\.coverCenter",
    "css.heroCard": r"\.heroCard",
    "css.coverMetrics": r"\.coverMetrics",
    "css.max_ink_token": r"--max-ink\s*:",
    "css.max_paper_token": r"--max-paper\s*:",
    "css.max_accent_token": r"--max-accent\s*:",
    "css.max_warm_token": r"--max-warm\s*:",
    "css.keep_korean_words": r"word-break\s*:\s*keep-all",
    "css.wrap_long_words": r"overflow-wrap\s*:\s*break-word",
}

BANNED_HTML_PATTERNS = {
    "wrong.miho_brand": r"MIHO\s+AI",
    "wrong.landscape": r"@page\s*\{[^}]*size\s*:\s*A4\s+landscape",
    "wrong.max_sports_admission": r"MAX\s+SPORTS\s+ADMISSION",
    "wrong.legacy_studentBox": r"\bstudentBox\b",
    "wrong.legacy_coverBottom": r"\bcoverBottom\b",
    "style.negative_letter_spacing": r"letter-spacing\s*:\s*-\s*[\d.]",
    "style.side_stripe": r"border-(left|right)\s*:\s*(?:[2-9]|\d{2,})(?:px|pt|mm)\s+solid",
    "style.absolute_footer": r"\.footer[^{]*\{[^}]*position\s*:\s*absolute",
}

BANNED_PDF_TEXT = (
    "MIHO AI",
    "MAX SPORTS ADMISSION",
    "source_thread",
    "profile_ready",
    "needs_review",
    "file://",
    "자료 기준",
    "학생 생활기록부 데이터",
    "생활기록부 데이터",
    "생활기록부 데이터 기준",
    "공식 전형자료",
    "대학 공식 전형자료",
    "맥스 수시엔진 산출 데이터",
    "수시엔진 산출 데이터",
    "산출 데이터 기준",
    "기준으로 구성",
    "기준으로 작성",
    "기준으로 분석",
    "제작 기준",
    "본 리포트는",
    "프리미엄",
    "인공지능",
    "AI",
)

MIN_REPORT_CARD_COUNT = 6
MIN_VISIBLE_TEXT_CHARS = 1_600
MIN_SUBSTANTIVE_SEGMENTS = 5
MIN_SUBSTANTIVE_SEGMENT_CHARS = 55
MAX_VISIBLE_TEXT_SEGMENT_CHARS = 230

LIFE_RECORD_EVIDENCE_TOOLS = {
    "life_record_lookup",
    "life_record_summary",
    "life_record_search",
    "life_record_verify",
}

HAKJONG_EVIDENCE_TOOLS = {
    "hakjong_profile",
    "qualitative_profile",
    "qualitative_profiles_md",
    "susi_engine",
    "admission_profile",
}


def validate_hakjong_report(
    *,
    html_path: Path,
    pdf_path: Path,
    student_name: str,
    university_name: str,
    department_name: str = "",
    track_name: str = "",
    student_stage: str = "",
    expected_pages: int = 4,
    evidence_tools: list[str] | None = None,
    page_image_paths: list[Path] | None = None,
    contact_sheet_path: Path | None = None,
) -> dict[str, Any]:
    """Return a strict validation report for a generated hakjong PDF."""
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}
    tools = evidence_tools or []
    normalized_stage = ""

    html = _read_text(html_path, errors, "html")
    if html:
        _validate_html(
            html,
            student_name=student_name,
            university_name=university_name,
            department_name=department_name,
            track_name=track_name,
            expected_pages=expected_pages,
            errors=errors,
            checks=checks,
        )
        visible_text = _visible_text(html)
        _validate_copy_quality(html, visible_text, errors=errors, checks=checks)
        normalized_stage = validate_stage_contract(
            student_stage=student_stage,
            visible_text=visible_text,
            evidence_tools=tools,
            errors=errors,
            checks=checks,
        )

    _validate_evidence(
        tools,
        student_stage=normalized_stage,
        errors=errors,
        checks=checks,
    )
    _validate_visual_artifacts(
        page_image_paths or [],
        contact_sheet_path,
        expected_pages=expected_pages,
        errors=errors,
        checks=checks,
    )

    _validate_pdf(
        pdf_path,
        student_name=student_name,
        university_name=university_name,
        department_name=department_name,
        track_name=track_name,
        expected_pages=expected_pages,
        errors=errors,
        warnings=warnings,
        checks=checks,
    )

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def _read_text(path: Path, errors: list[str], label: str) -> str:
    if not path.is_file():
        errors.append(f"{label} file does not exist: {path}")
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append(f"{label} file is not UTF-8 text: {path}")
    except OSError as exc:
        errors.append(f"{label} file could not be read: {exc}")
    return ""


def _validate_html(
    html: str,
    *,
    student_name: str,
    university_name: str,
    department_name: str,
    track_name: str,
    expected_pages: int,
    errors: list[str],
    checks: dict[str, Any],
) -> None:
    missing = [
        name
        for name, pattern in REQUIRED_HTML_PATTERNS.items()
        if not _regex_search(pattern, html)
    ]
    if missing:
        errors.append("locked premium_hakjong_report template markers missing: " + ", ".join(missing))

    banned = [
        name
        for name, pattern in BANNED_HTML_PATTERNS.items()
        if _regex_search(pattern, html, flags=re.IGNORECASE)
    ]
    if banned:
        errors.append("non-locked or wrong template markers found: " + ", ".join(banned))

    for label, value in _expected_terms(
        student_name=student_name,
        university_name=university_name,
        department_name=department_name,
        track_name=track_name,
    ):
        if value and value not in html:
            errors.append(f"html missing {label}: {value}")

    for label, value in (
        ("brand", BRAND_TEXT),
        ("title", REPORT_TITLE),
        ("audience", AUDIENCE_LABEL),
    ):
        if value not in html:
            errors.append(f"html missing {label}: {value}")

    page_count = len(re.findall(r'<section\s+class=["\'][^"\']*\bpage\b', html))
    checks["html_page_sections"] = page_count
    if page_count != expected_pages:
        errors.append(f"html page section count {page_count} != expected {expected_pages}")

    logo_tags = re.findall(r"<img\b[^>]*\blogo\b[^>]*>", html, flags=re.IGNORECASE)
    checks["logo_image_count"] = len(logo_tags)
    if not any(re.search(r'\bsrc=["\'][^"\']+["\']', tag, flags=re.IGNORECASE) for tag in logo_tags):
        errors.append("logo image with non-empty src is required for the locked MAX report template")

    footer_count = len(re.findall(r'class=["\'][^"\']*\bfooter\b', html))
    checks["footer_count"] = footer_count
    if footer_count < expected_pages:
        errors.append(f"footer count {footer_count} < expected page count {expected_pages}")

    if "{{" in html or "}}" in html:
        errors.append("html still contains unresolved template placeholders")


def _validate_copy_quality(
    html: str,
    visible_text: list[str],
    *,
    errors: list[str],
    checks: dict[str, Any],
) -> None:
    card_count = len(re.findall(r'class=["\'][^"\']*\bcard\b', html))
    checks["report_card_count"] = card_count
    if card_count < MIN_REPORT_CARD_COUNT:
        errors.append(
            f"report card count {card_count} < required {MIN_REPORT_CARD_COUNT}; "
            "split analysis into fixed premium report cards"
        )

    long_segments = [
        segment
        for segment in visible_text
        if len(segment) > MAX_VISIBLE_TEXT_SEGMENT_CHARS
    ]
    checks["long_text_segments"] = len(long_segments)
    if long_segments:
        errors.append(
            "visible copy contains overlong text blocks; split wording into concise Korean report sections"
        )

    visible_chars = sum(len(segment) for segment in visible_text)
    substantive_segments = sum(1 for segment in visible_text if len(segment) >= MIN_SUBSTANTIVE_SEGMENT_CHARS)
    checks["visible_text_chars"] = visible_chars
    checks["substantive_text_segments"] = substantive_segments
    if visible_chars < MIN_VISIBLE_TEXT_CHARS or substantive_segments < MIN_SUBSTANTIVE_SEGMENTS:
        errors.append(
            "substantive report copy is too shallow; expand school-specific evaluation and student evidence analysis"
        )

    for banned in BANNED_PDF_TEXT:
        if banned in " ".join(visible_text):
            errors.append(f"html visible text contains banned student-facing wording: {banned}")


def _validate_pdf(
    pdf_path: Path,
    *,
    student_name: str,
    university_name: str,
    department_name: str,
    track_name: str,
    expected_pages: int,
    errors: list[str],
    warnings: list[str],
    checks: dict[str, Any],
) -> None:
    if not pdf_path.is_file():
        errors.append(f"pdf file does not exist: {pdf_path}")
        return

    info = _pdf_info(pdf_path)
    if info.get("error"):
        errors.append(str(info["error"]))
    else:
        checks["pdf_pages"] = info.get("pages")
        checks["pdf_width"] = info.get("width")
        checks["pdf_height"] = info.get("height")
        if info.get("pages") != expected_pages:
            errors.append(f"pdf page count {info.get('pages')} != expected {expected_pages}")
        width = float(info.get("width") or 0)
        height = float(info.get("height") or 0)
        if width <= 0 or height <= 0:
            errors.append("pdf page size could not be parsed")
        elif width > height:
            errors.append("pdf is landscape; locked hakjong report must be A4 portrait")

    text = _pdf_text(pdf_path)
    if text.get("error"):
        warnings.append(str(text["error"]))
        return
    body = str(text.get("text") or "")
    for label, value in _expected_terms(
        student_name=student_name,
        university_name=university_name,
        department_name=department_name,
        track_name=track_name,
    ):
        if value and value not in body:
            errors.append(f"pdf text missing {label}: {value}")
    if BRAND_TEXT not in body:
        errors.append(f"pdf text missing brand: {BRAND_TEXT}")
    for banned in BANNED_PDF_TEXT:
        if banned in body:
            errors.append(f"pdf text contains banned internal/wrong marker: {banned}")


def _validate_evidence(
    evidence_tools: list[str],
    *,
    student_stage: str,
    errors: list[str],
    checks: dict[str, Any],
) -> None:
    normalized = {str(tool).strip() for tool in evidence_tools if str(tool).strip()}
    checks["evidence_tools"] = sorted(normalized)
    needs_life_record = student_stage in {"grade3", "graduate"} or not student_stage
    has_student_context = bool(normalized & LIFE_RECORD_EVIDENCE_TOOLS) or has_early_context_evidence(normalized)
    if needs_life_record and not (normalized & LIFE_RECORD_EVIDENCE_TOOLS):
        errors.append(
            "missing life-record evidence tool; use life_record_lookup/summary/search before packaging"
        )
    elif not needs_life_record and not has_student_context:
        errors.append("missing student context evidence; use consultation or life-record evidence before packaging")
    if not any(_matches_hakjong_evidence(tool) for tool in normalized):
        errors.append(
            "missing hakjong/admission-profile evidence; attach qualitative profile or susi_engine evidence"
        )


def _validate_visual_artifacts(
    page_image_paths: list[Path],
    contact_sheet_path: Path | None,
    *,
    expected_pages: int,
    errors: list[str],
    checks: dict[str, Any],
) -> None:
    checks["page_image_count"] = len(page_image_paths)
    if len(page_image_paths) != expected_pages:
        errors.append(f"page image count {len(page_image_paths)} != expected {expected_pages}")
    for path in page_image_paths:
        _validate_artifact(path, "page image", errors)
    if contact_sheet_path is None:
        errors.append("contact sheet image is required for final visual QA")
    else:
        _validate_artifact(contact_sheet_path, "contact sheet", errors)


def _pdf_info(pdf_path: Path) -> dict[str, Any]:
    if shutil.which("pdfinfo") is None:
        return {"error": "pdfinfo is not available"}
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": f"pdfinfo failed: {exc}"}
    if result.returncode != 0:
        return {"error": f"pdfinfo failed: {result.stderr.strip() or result.stdout.strip()}"}
    return _parse_pdfinfo(result.stdout)


def _parse_pdfinfo(output: str) -> dict[str, Any]:
    pages = None
    width = None
    height = None
    for line in output.splitlines():
        if line.startswith("Pages:"):
            pages = _int_or_none(line.split(":", 1)[1].strip())
        elif line.startswith("Page size:"):
            match = _regex_search(r"([\d.]+)\s+x\s+([\d.]+)\s+pts", line)
            if match:
                width = float(match.group(1))
                height = float(match.group(2))
    return {"pages": pages, "width": width, "height": height}


def _pdf_text(pdf_path: Path) -> dict[str, Any]:
    if shutil.which("pdftotext") is None:
        return {"error": "pdftotext is not available"}
    try:
        result = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": f"pdftotext failed: {exc}"}
    if result.returncode != 0:
        return {"error": f"pdftotext failed: {result.stderr.strip() or result.stdout.strip()}"}
    return {"text": result.stdout}


def _expected_terms(
    *,
    student_name: str,
    university_name: str,
    department_name: str,
    track_name: str,
) -> list[tuple[str, str]]:
    return [
        ("student_name", student_name.strip()),
        ("university_name", university_name.strip()),
        ("department_name", department_name.strip()),
        ("track_name", track_name.strip()),
    ]


def _regex_search(pattern: str, text: str, *, flags: int = 0) -> re.Match[str] | None:
    return re.compile(pattern, flags).search(text)


def _visible_text(html: str) -> list[str]:
    without_assets = re.sub(r"<(style|script)\b[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    without_comments = re.sub(r"<!--.*?-->", " ", without_assets, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "\n", without_comments)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return [segment.strip() for segment in text.splitlines() if segment.strip()]


def _matches_hakjong_evidence(tool: str) -> bool:
    return tool in HAKJONG_EVIDENCE_TOOLS or tool.startswith("hakjong_") or "qualitative" in tool


def _validate_artifact(path: Path, label: str, errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"{label} does not exist: {path}")
        return
    try:
        size = path.stat().st_size
    except OSError as exc:
        errors.append(f"{label} could not be stat'ed: {exc}")
        return
    if size < 10_000:
        errors.append(f"{label} is too small for visual QA: {path}")


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
