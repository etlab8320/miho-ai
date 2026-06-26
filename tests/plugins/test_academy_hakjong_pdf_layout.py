"""Layout regression tests for hakjong report PDFs."""

from __future__ import annotations

from pathlib import Path

import pytest

import plugins.academy_ops.hakjong_report_tool as report_tool
from plugins.academy_ops.pdf_layout_contract import footer_layout_errors


fitz = pytest.importorskip("fitz")


def _write_pdf(path: Path, pages: list[list[tuple[float, str]]]) -> None:
    doc = fitz.open()
    for page_blocks in pages:
        page = doc.new_page(width=595.92, height=842.88)
        for y, text in page_blocks:
            page.insert_text((36, y), text, fontsize=9)
    doc.save(path)
    doc.close()


def test_footer_layout_detects_orphaned_footer_page(tmp_path: Path) -> None:
    pdf = tmp_path / "orphan-footer.pdf"
    _write_pdf(
        pdf,
            [
                [
                    (80, "김동하 대전대학교 본문"),
                    (810, "MAX academy report 3"),
                ],
                [(18, "MAX academy report 3")],
            ],
        )

    errors = footer_layout_errors(pdf, expected_pages=1)

    assert any("예상 1페이지보다 많은 2페이지" in error for error in errors)
    assert any("2페이지 footer가 하단 고정 위치" in error for error in errors)
    assert any("footer만 다음 페이지 상단" in error for error in errors)


def test_footer_layout_passes_bottom_anchored_footer(tmp_path: Path) -> None:
    pdf = tmp_path / "anchored-footer.pdf"
    _write_pdf(
        pdf,
            [
                [
                    (80, "김동하 대전대학교 본문"),
                    (810, "MAX academy report 3"),
                ],
            ],
        )

    assert footer_layout_errors(pdf, expected_pages=1) == []


def test_hakjong_physical_validation_blocks_footer_orphan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tmp_path / "orphan-footer.pdf"
    _write_pdf(
        pdf,
            [
                [
                    (80, "김동하 대전대학교 맥스체대입시 일산교육원 본문"),
                    (810, "MAX academy report 3"),
                ],
                [(18, "MAX academy report 3")],
            ],
        )
    monkeypatch.setattr(
        report_tool._contract,
        "_pdf_info",
        lambda _path: {"width": 595.92, "height": 842.88, "pages": 2},
    )
    monkeypatch.setattr(
        report_tool._contract,
        "_pdf_text",
        lambda _path: {"text": "김동하 대전대학교 맥스체대입시 일산교육원"},
    )
    monkeypatch.setattr(
        report_tool._contract,
        "truncation_errors",
        lambda _content, _body, _errors: None,
    )
    content = {
        "strategy_section": {
            "gap_plan": {
                "subjects": [],
            },
        },
    }
    errors: list[str] = []

    report_tool._validate_pdf_physical(
        pdf,
        content=content,
        student_name="김동하",
        university_names=["대전대학교"],
        errors=errors,
    )

    assert any("footer" in error for error in errors)


def test_hakjong_template_uses_fixed_page_height() -> None:
    template = report_tool._TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "height: 297mm" in template
    assert "box-sizing: border-box" in template
    assert "min-height: 297mm" not in template
