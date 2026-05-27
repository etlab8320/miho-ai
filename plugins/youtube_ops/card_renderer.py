"""Render YouTube summary cards to PNG."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

from plugins.academy_ops.student_card_capture import (
    StudentCardCaptureError,
    capture_html_to_png,
    find_browser_executable,
)
from plugins.academy_ops.student_card_fonts import GOYANG_LICENSE_NOTE, goyang_font_css

from .card_template import render_card_html
from .models import SummaryResult


class YouTubeCardRenderError(RuntimeError):
    pass


def render_summary_card_png(summary: SummaryResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "summary_card.html"
    png_path = output_dir / "summary_card.png"
    html_path.write_text(
        render_card_html(summary, font_css=goyang_font_css()),
        encoding="utf-8",
    )
    try:
        capture_html_to_png(html_path, png_path, width=1200, height=_capture_height(html_path, summary))
    except StudentCardCaptureError as exc:
        raise YouTubeCardRenderError(str(exc)) from exc
    if not png_path.exists():
        raise YouTubeCardRenderError("유튜브 카드 이미지 파일이 생성되지 않았어.")
    return png_path


def font_license_note() -> str:
    return GOYANG_LICENSE_NOTE


def _estimate_card_height(summary: SummaryResult) -> int:
    groups = [
        summary.summary_lines,
        summary.important_points,
        summary.lessons,
        summary.practical_takeaways,
    ]
    text_units = sum(max(1, (len(item) + 28) // 29) for group in groups for item in group)
    section_count = sum(1 for group in groups if group)
    title_units = max(1, (len(summary.short_title) + 11) // 12)
    topic_units = max(1, (len(summary.topic) + 40) // 41)
    height = 470 + (title_units * 44) + (topic_units * 36) + (section_count * 88) + (text_units * 42)
    if summary.tags:
        height += 80
    return max(760, min(1900, height))


def _capture_height(html_path: Path, summary: SummaryResult) -> int:
    measured = _measure_html_height(html_path)
    if measured:
        return max(760, min(1900, measured + 72))
    return _estimate_card_height(summary)


def _measure_html_height(html_path: Path) -> int:
    browser = find_browser_executable()
    if browser is None:
        return 0
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1200,900",
        "--dump-dom",
        html_path.as_uri(),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if result.returncode != 0:
        return 0
    match = re.search(r'data-render-height="(\d+)"', result.stdout)
    return int(match.group(1)) if match else 0
