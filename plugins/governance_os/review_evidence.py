"""Evidence collection for Governance OS review gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .review_artifact_inspection import (
    artifact_inspection_failures,
    inspect_artifact_paths,
)

_PATH_FIELDS = (
    "file_path",
    "artifact_path",
    "pdf_path",
    "html_path",
    "manifest_path",
    "contact_sheet_path",
    "review_path",
)
_LIST_PATH_FIELDS = ("source_paths", "artifact_paths", "page_images")
_MAX_TEXT_CHARS = 80_000


def build_review_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Collect local artifact evidence for LLM reviewers without judging content."""

    paths: dict[str, dict[str, Any]] = {}
    json_manifests: dict[str, dict[str, Any]] = {}
    missing_paths: list[str] = []
    for path_text in _extract_path_values(payload):
        path = Path(path_text)
        info = _path_info(path)
        paths[str(path)] = info
        if not info["exists"]:
            missing_paths.append(str(path))
            continue
        if path.suffix.lower() == ".json":
            manifest = _json_summary(path)
            if manifest is not None:
                json_manifests[str(path)] = manifest
        elif path.suffix.lower() in {".md", ".txt"}:
            info.update(_text_summary(path))
    return {
        "paths": paths,
        "missing_paths": missing_paths,
        "json_manifests": json_manifests,
        "artifact_inspections": inspect_artifact_paths(paths),
    }


def review_evidence_required(payload: dict[str, Any], reviewer: dict[str, Any]) -> bool:
    return _truthy(payload.get("evidence_required")) or _truthy(reviewer.get("evidence_required"))


def review_evidence_failures(evidence: dict[str, Any]) -> tuple[str, ...]:
    missing = evidence.get("missing_paths")
    failures: list[str] = []
    if isinstance(missing, list):
        failures.extend(f"review evidence path missing: {path}" for path in missing)
    failures.extend(artifact_inspection_failures(evidence))
    return tuple(failures)


def _extract_path_values(payload: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for field in _PATH_FIELDS:
        _append_path(values, payload.get(field))
    for field in _LIST_PATH_FIELDS:
        raw = payload.get(field)
        if isinstance(raw, (list, tuple, set)):
            for item in raw:
                _append_path(values, item)
    media_tag = str(payload.get("media_tag") or "")
    if media_tag.startswith("MEDIA:"):
        _append_path(values, media_tag.removeprefix("MEDIA:"))
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return tuple(unique)


def _append_path(values: list[str], value: Any) -> None:
    text = str(value or "").strip().strip("`")
    if text:
        values.append(text)


def _path_info(path: Path) -> dict[str, Any]:
    exists = path.exists()
    info: dict[str, Any] = {
        "exists": exists,
        "is_file": path.is_file() if exists else False,
        "suffix": path.suffix.lower(),
        "size_bytes": 0,
    }
    if exists and path.is_file():
        try:
            info["size_bytes"] = path.stat().st_size
        except OSError:
            info["size_bytes"] = 0
    return info


def _json_summary(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8")[:_MAX_TEXT_CHARS])
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    summary: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            summary[key] = value
        elif isinstance(value, list):
            summary[key] = len(value)
        elif isinstance(value, dict):
            summary[key] = sorted(str(item) for item in value)[:20]
    return summary


def _text_summary(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")[:_MAX_TEXT_CHARS]
    except OSError:
        return {}
    lines = text.splitlines()
    return {
        "line_count": len(lines),
        "heading_count": sum(1 for line in lines if line.lstrip().startswith("#")),
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "required"}
