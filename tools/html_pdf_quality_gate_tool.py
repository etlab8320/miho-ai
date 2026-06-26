"""HTML-first PDF quality gate tool for Korean client-facing artifacts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.html_pdf_review_contract import (
    base_checked as _base_checked,
    visual_review as _visual_review,
    visual_review_failed as _visual_review_failed,
    visual_review_required as _visual_review_required,
)
from tools.registry import registry, tool_result


HTML_PDF_QUALITY_GATE_SCHEMA = {
    "name": "html_pdf_quality_gate",
    "description": (
        "Render a self-contained HTML artifact to PDF, scrub metadata, create page previews, "
        "and return a structured visual QA contract. Use for new Korean counseling, guide, "
        "training-program, or business PDFs; if visual QA fails, run html_pdf_autocorrect "
        "and rerender before media_delivery_contract."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "html_path": {
                "type": "string",
                "description": "Path to the self-contained source HTML file.",
            },
            "pdf_path": {
                "type": "string",
                "description": "Target PDF path. Defaults to html_path with .pdf suffix.",
            },
            "engine": {
                "type": "string",
                "enum": ["auto", "chrome", "playwright", "vivliostyle"],
                "description": "PDF rendering engine.",
            },
            "preview_dir": {
                "type": "string",
                "description": "Optional directory for page PNGs and contact sheet.",
            },
            "timeout": {
                "type": "integer",
                "description": "Render timeout seconds.",
            },
            "visual_review": {
                "oneOf": [{"type": "object"}, {"type": "string"}],
                "description": (
                    "Vision/LLM review result for the generated contact sheet. "
                    "Must include status=pass before the PDF is deliverable."
                ),
            },
        },
        "required": ["html_path"],
    },
}


def html_pdf_quality_gate_tool(args: dict[str, Any]) -> str:
    html_path = _input_path(args.get("html_path"))
    if not html_path:
        return _failed("HTML 원본 파일 경로가 비어 있습니다.")
    if not html_path.is_file():
        return _failed("HTML 원본 파일을 찾지 못했습니다.", html_path=str(html_path))

    pdf_path = _pdf_path(args.get("pdf_path"), html_path)
    preview_dir = _optional_path(args.get("preview_dir"))
    engine = _engine(args.get("engine"))
    timeout = _timeout(args.get("timeout"))
    runner = _runner_script()
    if runner is None:
        return _failed(
            "HTML-first PDF 품질 게이트 실행 파일을 찾지 못했습니다.",
            html_path=str(html_path),
            pdf_path=str(pdf_path),
        )

    command = [
        sys.executable,
        str(runner),
        "--html",
        str(html_path),
        "--pdf",
        str(pdf_path),
        "--engine",
        engine,
        "--timeout",
        str(timeout),
    ]
    if preview_dir is not None:
        command.extend(["--preview-dir", str(preview_dir)])

    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout + 10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _failed(
            "PDF 품질 게이트 실행 시간이 초과되었습니다.",
            html_path=str(html_path),
            pdf_path=str(pdf_path),
        )
    except OSError as exc:
        return _failed(
            f"PDF 품질 게이트 실행에 실패했습니다: {exc}",
            html_path=str(html_path),
            pdf_path=str(pdf_path),
        )
    payload = _load_json(proc.stdout) or _load_json(proc.stderr) or {}
    ok = proc.returncode == 0 and bool(payload.get("ok")) and pdf_path.is_file()
    if not ok:
        return _failed(
            _failure_message(proc, payload),
            html_path=str(html_path),
            pdf_path=str(pdf_path),
            gate_payload=payload,
        )

    visual_review = _visual_review(args.get("visual_review"))
    if not visual_review["provided"]:
        return _visual_review_required(
            html_path=html_path,
            pdf_path=pdf_path,
            payload=payload,
        )
    if not visual_review["passed"]:
        return _visual_review_failed(
            html_path=html_path,
            pdf_path=pdf_path,
            payload=payload,
            visual_review=visual_review,
        )

    return tool_result(
        success=True,
        html_path=str(html_path),
        pdf_path=str(pdf_path.resolve()),
        artifact_path=str(pdf_path.resolve()),
        contact_sheet_path=str(payload.get("contact_sheet") or ""),
        page_images=payload.get("page_images") or [],
        pdf_quality_gate=payload,
        visual_review=visual_review["raw"],
        reviewer={
            "name": "html_pdf_quality_review",
            "status": "pass",
            "checked": _base_checked() + ["visual_review"],
            "warnings": visual_review["warnings"],
            "evidence_required": True,
        },
        message_ko="HTML-first PDF 품질 게이트를 통과했습니다.",
    )


def check_html_pdf_quality_gate_requirements() -> bool:
    return _runner_script() is not None


def _input_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return Path(text).expanduser().resolve()


def _optional_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text).expanduser().resolve() if text else None


def _pdf_path(value: Any, html_path: Path) -> Path:
    text = str(value or "").strip()
    if text:
        return Path(text).expanduser().resolve()
    return html_path.with_suffix(".pdf").resolve()


def _engine(value: Any) -> str:
    text = str(value or "auto").strip()
    return text if text in {"auto", "chrome", "playwright", "vivliostyle"} else "auto"


def _timeout(value: Any) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return 90
    return min(max(seconds, 10), 240)


def _runner_script() -> Path | None:
    candidates = (
        os.environ.get("MIHO_HTML_PDF_QUALITY_GATE_SCRIPT", ""),
        str(Path(__file__).resolve().parents[1] / "scripts" / "html_pdf_quality_gate.py"),
        str(
            Path.home()
            / ".miho"
            / "skills"
            / "productivity"
            / "korean-business-pdf-artifacts"
            / "scripts"
            / "html_pdf_quality_gate.py"
        ),
    )
    for raw in candidates:
        path = Path(raw).expanduser() if raw else None
        if path and path.is_file():
            return path.resolve()
    return None


def _load_json(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _failure_message(proc: subprocess.CompletedProcess[str], payload: dict[str, Any]) -> str:
    if payload.get("error"):
        return str(payload["error"])
    detail = (proc.stderr or proc.stdout or "").strip()
    if detail:
        return f"PDF 품질 게이트가 통과하지 못했습니다: {detail[:500]}"
    return "PDF 품질 게이트가 통과하지 못했습니다."


def _failed(
    message_ko: str,
    *,
    html_path: str = "",
    pdf_path: str = "",
    gate_payload: dict[str, Any] | None = None,
) -> str:
    return tool_result(
        success=False,
        html_path=html_path,
        pdf_path=pdf_path,
        artifact_path=pdf_path,
        pdf_quality_gate=gate_payload or {},
        errors=[message_ko],
        reviewer={
            "name": "html_pdf_quality_review",
            "status": "fail",
            "checked": ["html_source", "pdf_render", "contact_sheet"],
        },
        message_ko=message_ko,
    )


registry.register(
    name="html_pdf_quality_gate",
    toolset="academy_ops",
    schema=HTML_PDF_QUALITY_GATE_SCHEMA,
    handler=lambda args, **kw: html_pdf_quality_gate_tool(args),
    check_fn=check_html_pdf_quality_gate_requirements,
    emoji="PDF",
    max_result_size_chars=40_000,
)
