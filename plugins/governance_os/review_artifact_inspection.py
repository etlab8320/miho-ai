"""Artifact inspection helpers for LLM Governance reviewers."""

from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import Any


_MAX_TEXT_CHARS = 12_000
_TEXT_SUFFIXES = {".html", ".htm", ".mhtml", ".mht", ".md", ".txt", ".csv"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def inspect_artifact_paths(paths: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    inspections: dict[str, dict[str, Any]] = {}
    for raw_path, info in paths.items():
        if not isinstance(info, dict) or not info.get("exists") or not info.get("is_file"):
            continue
        path = Path(raw_path)
        inspections[raw_path] = inspect_artifact_path(path)
    return inspections


def inspect_artifact_path(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _inspect_pdf(path)
    if suffix in _TEXT_SUFFIXES:
        return _inspect_text(path, kind=_kind_for_text_suffix(suffix))
    if suffix in _IMAGE_SUFFIXES:
        return _inspect_image(path)
    if suffix == ".json":
        return {"kind": "json", "opened": True, "inspection_required": False}
    return {
        "kind": suffix.lstrip(".") or "file",
        "opened": path.is_file(),
        "inspection_required": False,
    }


def artifact_inspection_failures(evidence: dict[str, Any]) -> tuple[str, ...]:
    inspections = evidence.get("artifact_inspections")
    if not isinstance(inspections, dict):
        return ()
    failures: list[str] = []
    for path, info in inspections.items():
        if not isinstance(info, dict):
            continue
        if info.get("inspection_required") and not info.get("opened"):
            failures.append(f"review artifact not inspectable: {path}")
    return tuple(failures)


def _inspect_pdf(path: Path) -> dict[str, Any]:
    base = {
        "kind": "pdf",
        "opened": False,
        "inspection_required": True,
        "page_count": 0,
        "text_sample": "",
    }
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {**base, "error_type": type(exc).__name__}
    basic = {
        **base,
        "opened": data.startswith(b"%PDF"),
        "header": data[:8].decode("latin-1", errors="replace"),
        "page_markers": len(re.findall(rb"/Type\s*/Page\b", data)),
        "extractor": "basic",
    }
    try:
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(str(path))
        sample_parts: list[str] = []
        for page_index in range(min(3, doc.page_count)):
            sample_parts.append(doc.load_page(page_index).get_text("text"))
        return {
            **basic,
            "opened": True,
            "page_count": doc.page_count,
            "text_sample": _compact_text("\n".join(sample_parts)),
            "extractor": "pymupdf",
        }
    except Exception as exc:
        return {**basic, "extract_error_type": type(exc).__name__}


def _inspect_text(path: Path, *, kind: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:_MAX_TEXT_CHARS]
    except OSError as exc:
        return {
            "kind": kind,
            "opened": False,
            "inspection_required": True,
            "error_type": type(exc).__name__,
        }
    plain = _strip_html(text) if kind in {"html", "mhtml"} else text
    return {
        "kind": kind,
        "opened": True,
        "inspection_required": True,
        "line_count": len(text.splitlines()),
        "text_sample": _compact_text(plain),
    }


def _inspect_image(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()[:64 * 1024]
    except OSError as exc:
        return {
            "kind": "image",
            "opened": False,
            "inspection_required": True,
            "error_type": type(exc).__name__,
        }
    width, height = _image_size(data)
    return {
        "kind": "image",
        "opened": bool(width and height),
        "inspection_required": True,
        "width": width,
        "height": height,
        "format": _image_format(data),
    }


def _image_size(data: bytes) -> tuple[int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8"):
        return _jpeg_size(data)
    return (0, 0)


def _jpeg_size(data: bytes) -> tuple[int, int]:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        length = int.from_bytes(data[index + 2 : index + 4], "big")
        if marker in {0xC0, 0xC2} and index + 8 < len(data):
            height = int.from_bytes(data[index + 5 : index + 7], "big")
            width = int.from_bytes(data[index + 7 : index + 9], "big")
            return (width, height)
        index += max(length + 2, 2)
    return (0, 0)


def _image_format(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpeg"
    return "unknown"


def _kind_for_text_suffix(suffix: str) -> str:
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".mhtml", ".mht"}:
        return "mhtml"
    return suffix.lstrip(".") or "text"


def _strip_html(text: str) -> str:
    without_scripts = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.I | re.S)
    return re.sub(r"<[^>]+>", " ", without_scripts)


def _compact_text(text: str) -> str:
    return " ".join(str(text or "").split())[:4_000]
