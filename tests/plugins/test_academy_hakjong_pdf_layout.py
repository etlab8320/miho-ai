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


def test_footer_layout_accepts_long_bottom_footnote_footer(tmp_path: Path) -> None:
    pdf = tmp_path / "long-footer.pdf"
    _write_pdf(
        pdf,
        [
            [
                (80, "김동하 대전대학교 본문"),
                (
                    806,
                    "성균관대학교 성균인재전형은 학생부종합평가에서 학교생활의 충실도를 중시하며 "
                    "특히 전공 관련 세특과 진로활동의 일관성을 높게 평가합니다. 1",
                ),
            ],
        ],
    )

    assert footer_layout_errors(pdf, expected_pages=1) == []


def test_hakjong_pdf_fit_uses_base_chromium_printer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path]] = []
    html = tmp_path / "report.html"
    pdf = tmp_path / "report.pdf"

    def fake_base_print(html_path: Path, pdf_path: Path) -> None:
        calls.append((html_path, pdf_path))
        pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

    def fake_render_pdf_fit(content, html_path, pdf_path, *, student_stage: str = "") -> str:
        report_tool._rendering._chromium_print_to_pdf(html_path, pdf_path)
        return "<html></html>"

    monkeypatch.setattr(report_tool, "_BASE_CHROMIUM_PRINT_TO_PDF", fake_base_print)
    monkeypatch.setattr(report_tool._rendering, "render_pdf_fit", fake_render_pdf_fit)

    rendered = report_tool._render_pdf_fit({}, html, pdf, student_stage="grade3")

    assert rendered == "<html></html>"
    assert calls == [(html, pdf)]


def test_hakjong_pdf_fit_keeps_compacting_when_footer_layout_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    rendered_steps: list[str] = []

    def fake_render_html(_content, body_class: str = "", student_stage: str = "") -> str:
        rendered_steps.append(body_class)
        return f"<html>{body_class or 'base'}:{student_stage}</html>"

    def fake_print(_html_path: Path, _pdf_path: Path) -> None:
        _pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

    def fake_footer_errors(_pdf_path: Path, *, expected_pages: int | None = None) -> list[str]:
        return [] if "compact2" in html_path.read_text(encoding="utf-8") else ["footer pushed"]

    monkeypatch.setattr(report_tool._rendering, "render_html", fake_render_html)
    monkeypatch.setattr(report_tool._rendering, "_chromium_print_to_pdf", fake_print)
    monkeypatch.setattr(report_tool._rendering._contract, "_pdf_info", lambda _path: {"pages": 4})
    monkeypatch.setattr(report_tool._rendering, "footer_layout_errors", fake_footer_errors)

    rendered = report_tool._rendering.render_pdf_fit(
        {"strategy_section": {"gap_plan": {"subjects": []}}},
        html_path,
        pdf_path,
        student_stage="grade3",
    )

    assert rendered_steps == ["", "compact1", "compact2"]
    assert rendered == "<html>compact2:grade3</html>"


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


def test_hakjong_physical_validation_ignores_gap_plan_hidden_checklist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    content = {
        "strategy_section": {
            "gap_plan": {"subjects": []},
            "checklist": {
                "bullets": [
                    "원서 제출 마감일 확인 및 여유있게 제출해야 한다는 숨김 체크리스트 문장",
                ],
            },
        }
    }
    monkeypatch.setattr(
        report_tool._contract,
        "_pdf_info",
        lambda _path: {"width": 595.92, "height": 842.88, "pages": 4},
    )
    monkeypatch.setattr(
        report_tool._contract,
        "_pdf_text",
        lambda _path: {"text": "김동하 대전대학교 맥스체대입시 일산교육원"},
    )
    monkeypatch.setattr(report_tool._rendering, "footer_layout_errors", lambda *_args, **_kwargs: [])
    errors: list[str] = []

    report_tool._validate_pdf_physical(
        pdf,
        content=content,
        student_name="김동하",
        university_names=["대전대학교"],
        errors=errors,
    )

    assert not any("원서 제출 마감일" in error for error in errors)


def test_hakjong_template_uses_fixed_page_height() -> None:
    template = report_tool._TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "height: 297mm" in template
    assert "box-sizing: border-box" in template
    assert "min-height: 297mm" not in template
