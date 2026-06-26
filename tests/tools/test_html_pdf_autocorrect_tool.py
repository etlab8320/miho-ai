"""Tests for HTML-first PDF layout autocorrection."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from toolsets import resolve_multiple_toolsets


def _json(raw: str) -> dict:
    return json.loads(raw)


def test_html_pdf_autocorrect_injects_print_layout_guards(tmp_path: Path) -> None:
    import tools.html_pdf_autocorrect_tool as tool

    importlib.reload(tool)
    html = tmp_path / "source.html"
    html.write_text(
        """
        <html>
          <head><title>상담자료</title></head>
          <body>
            <section class="card"><h1>4개월 시즌 운동</h1><p>본문입니다.</p></section>
            <footer style="position: fixed; bottom: -12px">맥스체대입시 확인용</footer>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    result = _json(
        tool.html_pdf_autocorrect_tool(
            {
                "html_path": str(html),
                "visual_review": {
                    "status": "fail",
                    "errors": ["footer가 페이지 밖으로 밀림", "줄 정렬이 흔들림"],
                },
            }
        )
    )

    corrected = Path(result["html_path"])
    content = corrected.read_text(encoding="utf-8")
    assert result["success"] is True
    assert corrected.is_file()
    assert corrected != html
    assert "miho-pdf-autocorrect" in content
    assert "break-inside: avoid" in content
    assert "overflow-wrap: anywhere" in content
    assert "position: running(miho-footer)" in content
    assert result["reviewer"]["status"] == "pass"
    assert "footer_guard" in result["reviewer"]["checked"]


def test_html_pdf_autocorrect_is_visible_to_discord_academy_toolsets() -> None:
    import tools.html_pdf_autocorrect_tool as tool
    from tools.registry import registry

    importlib.reload(tool)

    entry = registry.get_entry("html_pdf_autocorrect")
    assert entry is not None
    assert entry.toolset == "academy_ops"
    assert "html_pdf_autocorrect" in resolve_multiple_toolsets(
        ["miho-discord", "academy_ops"]
    )
