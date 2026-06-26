"""Tests for the HTML-first PDF quality gate tool."""

from __future__ import annotations

import importlib
import json
import shutil
from pathlib import Path

import pytest

from toolsets import resolve_multiple_toolsets


def _json(raw: str) -> dict:
    return json.loads(raw)


def test_html_pdf_quality_gate_tool_uses_configured_runner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = tmp_path / "fake_gate.py"
    runner.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "pdf = Path(sys.argv[sys.argv.index('--pdf') + 1])\n"
        "pdf.write_bytes(b'%PDF-1.7 fake')\n"
        "preview = pdf.parent / 'preview' / 'contact_sheet.png'\n"
        "preview.parent.mkdir(parents=True, exist_ok=True)\n"
        "preview.write_bytes(b'png')\n"
        "print(json.dumps({"
        "'ok': True, 'pdf_path': str(pdf), 'contact_sheet': str(preview), "
        "'page_count': 1, 'forbidden_byte_hits': []"
        "}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MIHO_HTML_PDF_QUALITY_GATE_SCRIPT", str(runner))

    import tools.html_pdf_quality_gate_tool as tool

    importlib.reload(tool)
    html = tmp_path / "source.html"
    pdf = tmp_path / "out.pdf"
    html.write_text("<html><body><h1>상담 PDF</h1></body></html>", encoding="utf-8")

    result = _json(
        tool.html_pdf_quality_gate_tool(
            {
                "html_path": str(html),
                "pdf_path": str(pdf),
                "engine": "auto",
                "visual_review": {
                    "status": "pass",
                    "checked": [
                        "line_alignment",
                        "footer_layout",
                        "no_text_overlap",
                        "design_quality",
                    ],
                    "summary": "상담용 PDF로 전달 가능",
                },
            }
        )
    )

    assert result["success"] is True
    assert result["artifact_path"] == str(pdf.resolve())
    assert result["pdf_quality_gate"]["ok"] is True
    assert result["contact_sheet_path"].endswith("contact_sheet.png")
    assert result["reviewer"]["name"] == "html_pdf_quality_review"
    assert result["reviewer"]["status"] == "pass"
    assert "visual_review" in result["reviewer"]["checked"]


def test_html_pdf_quality_gate_requires_visual_review_before_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = tmp_path / "fake_gate.py"
    runner.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "pdf = Path(sys.argv[sys.argv.index('--pdf') + 1])\n"
        "pdf.write_bytes(b'%PDF-1.7 fake')\n"
        "preview = pdf.parent / 'preview' / 'contact_sheet.png'\n"
        "preview.parent.mkdir(parents=True, exist_ok=True)\n"
        "preview.write_bytes(b'png')\n"
        "print(json.dumps({"
        "'ok': True, 'pdf_path': str(pdf), 'contact_sheet': str(preview), "
        "'review_prompt': 'contact sheet를 보고 footer와 겹침을 검수해줘', "
        "'page_count': 1, 'forbidden_byte_hits': []"
        "}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MIHO_HTML_PDF_QUALITY_GATE_SCRIPT", str(runner))

    import tools.html_pdf_quality_gate_tool as tool

    importlib.reload(tool)
    html = tmp_path / "source.html"
    pdf = tmp_path / "out.pdf"
    html.write_text("<html><body><h1>상담 PDF</h1></body></html>", encoding="utf-8")

    result = _json(
        tool.html_pdf_quality_gate_tool(
            {
                "html_path": str(html),
                "pdf_path": str(pdf),
                "engine": "auto",
            }
        )
    )

    assert result["success"] is False
    assert result["pdf_path"] == str(pdf.resolve())
    assert result["contact_sheet_path"].endswith("contact_sheet.png")
    assert result["reviewer"]["status"] == "retry_needed"
    assert "vision_analyze" in result["reviewer"]["retry_tools"]
    assert result["reviewer"]["retry_args"][0]["image_url"].endswith("contact_sheet.png")
    assert "media_delivery_contract" in result["reviewer"]["retry_tools"]


def test_html_pdf_quality_gate_failed_visual_review_requests_autocorrect(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = tmp_path / "fake_gate.py"
    runner.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "pdf = Path(sys.argv[sys.argv.index('--pdf') + 1])\n"
        "pdf.write_bytes(b'%PDF-1.7 fake')\n"
        "preview = pdf.parent / 'preview' / 'contact_sheet.png'\n"
        "preview.parent.mkdir(parents=True, exist_ok=True)\n"
        "preview.write_bytes(b'png')\n"
        "print(json.dumps({"
        "'ok': True, 'pdf_path': str(pdf), 'contact_sheet': str(preview), "
        "'review_prompt': 'footer와 줄맞춤을 검수해줘', "
        "'page_count': 1, 'forbidden_byte_hits': []"
        "}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MIHO_HTML_PDF_QUALITY_GATE_SCRIPT", str(runner))

    import tools.html_pdf_quality_gate_tool as tool

    importlib.reload(tool)
    html = tmp_path / "source.html"
    pdf = tmp_path / "out.pdf"
    html.write_text("<html><body><footer>맥스체대입시</footer></body></html>", encoding="utf-8")

    result = _json(
        tool.html_pdf_quality_gate_tool(
            {
                "html_path": str(html),
                "pdf_path": str(pdf),
                "engine": "auto",
                "visual_review": {
                    "status": "fail",
                    "errors": ["footer가 페이지 밖으로 밀림", "본문 줄 정렬 흔들림"],
                },
            }
        )
    )

    assert result["success"] is False
    assert result["next_action"] == "revise_html_and_retry"
    retry_tools = result["reviewer"]["retry_tools"]
    assert retry_tools == [
        "html_pdf_autocorrect",
        "html_pdf_quality_gate",
        "vision_analyze",
        "html_pdf_quality_gate",
        "media_delivery_contract",
    ]
    assert result["reviewer"]["retry_args"][0]["html_path"] == str(html)
    assert "footer" in str(result["reviewer"]["retry_args"][0]["visual_review"])


def test_html_pdf_quality_gate_tool_is_visible_to_discord_academy_toolsets() -> None:
    import tools.html_pdf_quality_gate_tool as tool
    from tools.registry import registry

    importlib.reload(tool)

    entry = registry.get_entry("html_pdf_quality_gate")
    assert entry is not None
    assert entry.toolset == "academy_ops"
    assert "html_pdf_quality_gate" in resolve_multiple_toolsets(
        ["miho-discord", "academy_ops"]
    )


def test_html_pdf_quality_gate_real_runner_renders_scrubbed_pdf(
    tmp_path: Path,
    monkeypatch,
) -> None:
    if not shutil.which("playwright"):
        pytest.skip("playwright CLI is required for the real PDF runner smoke")
    monkeypatch.delenv("MIHO_HTML_PDF_QUALITY_GATE_SCRIPT", raising=False)

    import tools.html_pdf_quality_gate_tool as tool

    importlib.reload(tool)
    html = tmp_path / "season.html"
    pdf = tmp_path / "season.pdf"
    html.write_text(
        (
            "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            "<style>@page{size:A4;margin:18mm 16mm 20mm}"
            "body{font-family:Arial,sans-serif;line-height:1.55;color:#111}"
            "h1{font-size:24px}p{font-size:13px}footer{margin-top:24px;font-size:10px}"
            "</style></head><body><h1>4개월 시즌 운동 프로그램</h1>"
            "<p>고강도 훈련은 목적에 맞춰 배치하고 회복일과 기록 측정일을 분리한다.</p>"
            "<p>월수목금토 기준으로 오후 훈련과 야간 훈련을 나누어 운영한다.</p>"
            "<footer>맥스체대입시 상담자료</footer></body></html>"
        ),
        encoding="utf-8",
    )

    result = _json(
        tool.html_pdf_quality_gate_tool(
            {
                "html_path": str(html),
                "pdf_path": str(pdf),
                "engine": "playwright",
                "timeout": 60,
                "visual_review": {
                    "status": "pass",
                    "checked": [
                        "line_alignment",
                        "footer_layout",
                        "no_text_overlap",
                        "design_quality",
                    ],
                },
            }
        )
    )

    gate = result["pdf_quality_gate"]
    assert result["success"] is True
    assert Path(result["artifact_path"]).is_file()
    assert Path(result["contact_sheet_path"]).is_file()
    assert gate["engine"] == "playwright"
    assert gate["ok"] is True
    assert gate["text_length"] > 0
    assert gate["layout_errors"] == []
    assert gate["forbidden_text_hits"] == []
    assert gate["forbidden_byte_hits"] == []
    scrubbed_keys = ("title", "author", "subject", "keywords", "creator", "producer")
    assert all(not str(gate["metadata"].get(key) or "").strip() for key in scrubbed_keys)
