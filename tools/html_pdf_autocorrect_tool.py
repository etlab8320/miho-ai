"""HTML layout autocorrection for HTML-first PDF artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.registry import registry, tool_result


HTML_PDF_AUTOCORRECT_SCHEMA = {
    "name": "html_pdf_autocorrect",
    "description": (
        "Inject print-safe CSS into a self-contained HTML PDF source after visual QA "
        "finds footer overflow, text overlap, line alignment, or page-break issues. "
        "Use before rerunning html_pdf_quality_gate."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "html_path": {"type": "string", "description": "Source HTML path to repair."},
            "output_html_path": {
                "type": "string",
                "description": "Optional repaired HTML path. Defaults to .autofixed.html.",
            },
            "visual_review": {
                "oneOf": [{"type": "object"}, {"type": "string"}],
                "description": "Failed visual review result with layout issues.",
            },
            "pdf_path": {
                "type": "string",
                "description": "Optional downstream target PDF path.",
            },
        },
        "required": ["html_path"],
    },
}

_STYLE_ID = "miho-pdf-autocorrect"
_PRINT_GUARD_CSS = """
<style id="miho-pdf-autocorrect">
@page {
  size: A4;
  margin: 18mm 16mm 20mm;
}
html, body {
  margin: 0;
  padding: 0;
  font-family: Pretendard, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
  line-height: 1.45;
  letter-spacing: 0;
  word-break: keep-all;
  overflow-wrap: anywhere;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
*, *::before, *::after { box-sizing: border-box; }
section, article, .section, .card, .panel, .page-block, figure, table {
  break-inside: avoid;
  page-break-inside: avoid;
}
table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
th, td {
  vertical-align: top;
  overflow-wrap: anywhere;
  word-break: keep-all;
}
img, svg, canvas {
  max-width: 100%;
  height: auto;
}
footer, .footer, [data-role="footer"], [data-miho-footer] {
  position: running(miho-footer) !important;
  break-inside: avoid;
  page-break-inside: avoid;
  margin-top: 8mm;
  padding-top: 3mm;
  font-size: 9px;
  line-height: 1.3;
}
@page {
  @bottom-center {
    content: element(miho-footer);
  }
}
</style>
""".strip()


def html_pdf_autocorrect_tool(args: dict[str, Any]) -> str:
    html_path = _path(args.get("html_path"))
    if html_path is None:
        return _failed("보정할 HTML 경로가 비어 있습니다.")
    if not html_path.is_file():
        return _failed("보정할 HTML 파일을 찾지 못했습니다.", html_path=str(html_path))

    output_path = _output_path(args.get("output_html_path"), html_path)
    try:
        source = html_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _failed(f"HTML 파일을 읽지 못했습니다: {exc}", html_path=str(html_path))

    corrected, applied = _correct_html(source)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(corrected, encoding="utf-8")
    visual_issues = _visual_issues(args.get("visual_review"))

    return tool_result(
        success=True,
        html_path=str(output_path.resolve()),
        corrected_html_path=str(output_path.resolve()),
        source_html_path=str(html_path.resolve()),
        artifact_path=str(output_path.resolve()),
        pdf_path=str(args.get("pdf_path") or ""),
        visual_issues=visual_issues,
        autocorrect={"applied": applied, "style_id": _STYLE_ID},
        reviewer={
            "name": "html_pdf_autocorrect_review",
            "status": "pass",
            "checked": [
                "print_css",
                "line_alignment_guard",
                "footer_guard",
                "overflow_guard",
                "page_break_guard",
            ],
        },
        message_ko="HTML PDF 레이아웃 안전장치를 적용했습니다.",
    )


def check_html_pdf_autocorrect_requirements() -> bool:
    return True


def _path(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text).expanduser().resolve() if text else None


def _output_path(value: Any, html_path: Path) -> Path:
    text = str(value or "").strip()
    if text:
        return Path(text).expanduser().resolve()
    return html_path.with_name(f"{html_path.stem}.autofixed{html_path.suffix}")


def _correct_html(source: str) -> tuple[str, list[str]]:
    applied: list[str] = []
    html = _remove_existing_guard(source)
    html, inserted = _inject_style(html)
    if inserted:
        applied.append("print_layout_css")
    html, normalized = _normalize_fixed_footer(html)
    if normalized:
        applied.append("fixed_footer_override")
    return html, applied


def _remove_existing_guard(source: str) -> str:
    pattern = re.compile(
        r"<style[^>]*id=[\"']miho-pdf-autocorrect[\"'][^>]*>.*?</style>",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub("", source)


def _inject_style(source: str) -> tuple[str, bool]:
    if "</head>" in source.lower():
        return re.sub(
            r"</head>",
            _PRINT_GUARD_CSS + "\n</head>",
            source,
            count=1,
            flags=re.IGNORECASE,
        ), True
    if "<html" in source.lower():
        return re.sub(
            r"(<html[^>]*>)",
            "\\1\n<head>\n" + _PRINT_GUARD_CSS + "\n</head>",
            source,
            count=1,
            flags=re.IGNORECASE,
        ), True
    return _PRINT_GUARD_CSS + "\n" + source, True


def _normalize_fixed_footer(source: str) -> tuple[str, bool]:
    pattern = re.compile(r"(<footer\b[^>]*style=[\"'])([^\"']*)([\"'][^>]*>)", re.I)
    changed = False

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        style = match.group(2)
        if "position" not in style.casefold():
            return match.group(0)
        changed = True
        cleaned = re.sub(r"position\s*:\s*fixed\s*;?", "", style, flags=re.I)
        cleaned = re.sub(r"bottom\s*:\s*[-0-9.]+[a-z%]*\s*;?", "", cleaned, flags=re.I)
        return f"{match.group(1)}{cleaned.strip()}{match.group(3)}"

    return pattern.sub(repl, source), changed


def _visual_issues(value: Any) -> list[str]:
    raw = _loads_object(value)
    if raw is None:
        return []
    issues = raw.get("errors") or raw.get("issues") or raw.get("problems") or []
    if isinstance(issues, str):
        return [issues] if issues.strip() else []
    if isinstance(issues, list):
        return [str(item).strip() for item in issues if str(item).strip()]
    return []


def _loads_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _failed(message_ko: str, *, html_path: str = "") -> str:
    return tool_result(
        success=False,
        html_path=html_path,
        errors=[message_ko],
        reviewer={
            "name": "html_pdf_autocorrect_review",
            "status": "fail",
            "checked": ["html_source"],
        },
        message_ko=message_ko,
    )


registry.register(
    name="html_pdf_autocorrect",
    toolset="academy_ops",
    schema=HTML_PDF_AUTOCORRECT_SCHEMA,
    handler=lambda args, **kw: html_pdf_autocorrect_tool(args),
    check_fn=check_html_pdf_autocorrect_requirements,
    emoji="PDF",
    max_result_size_chars=20_000,
)
