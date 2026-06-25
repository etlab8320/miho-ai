"""Canonical manifest helpers for hakjong report PDFs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import hakjong_report_contract as _contract


HAKJONG_MANIFEST_VERSION = 2
HAKJONG_GENERATOR = "academy_hakjong_report_package"


def collect_pdf_checks(pdf_path: Path) -> dict[str, Any]:
    """Collect the physical PDF facts used to lock a report as canonical."""
    info = _contract._pdf_info(pdf_path)
    text_result = _contract._pdf_text(pdf_path)
    text = "" if text_result.get("error") else str(text_result.get("text") or "")
    checks: dict[str, Any] = {
        "size_bytes": pdf_path.stat().st_size if pdf_path.exists() else 0,
        "pages": info.get("pages"),
        "width": info.get("width"),
        "height": info.get("height"),
        "printed_text_chars": len(text.strip()),
    }
    if info.get("error"):
        checks["pdfinfo_error"] = info["error"]
    if text_result.get("error"):
        checks["pdftotext_error"] = text_result["error"]
    return checks


def build_hakjong_manifest(
    *,
    pdf_path: Path,
    html_path: Path,
    student_name: str,
    university_names: list[str],
    student_stage: str,
    schema_checks: dict[str, Any],
    pdf_checks: dict[str, Any],
    live_research_applied: bool,
    live_research_bundle_path: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "manifest_version": HAKJONG_MANIFEST_VERSION,
        "generator": HAKJONG_GENERATOR,
        "pdf_path": str(pdf_path),
        "html_path": str(html_path),
        "student_name": student_name,
        "university_names": university_names,
        "student_stage": student_stage,
        "live_research_applied": live_research_applied,
        "live_research_bundle_path": live_research_bundle_path,
        "checks": {
            "schema": schema_checks,
            "pdf": pdf_checks,
        },
    }


def is_canonical_hakjong_manifest(manifest: dict[str, Any]) -> bool:
    if not isinstance(manifest, dict) or manifest.get("ok") is not True:
        return False
    if manifest.get("manifest_version") != HAKJONG_MANIFEST_VERSION:
        return False
    if manifest.get("generator") != HAKJONG_GENERATOR:
        return False
    checks = manifest.get("checks")
    if not isinstance(checks, dict):
        return False
    schema = checks.get("schema")
    pdf = checks.get("pdf")
    if not isinstance(schema, dict) or not isinstance(pdf, dict):
        return False
    if not schema.get("evidence_tools"):
        return False
    if not isinstance(schema.get("visible_text_chars"), int):
        return False
    if not isinstance(pdf.get("pages"), int):
        return False
    return isinstance(pdf.get("printed_text_chars"), int) and pdf["printed_text_chars"] > 0
