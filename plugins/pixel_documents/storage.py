"""Storage helpers for pixel document evidence manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home


SCHEMA_VERSION = "pixel_document_evidence.v1"


def pixel_documents_root() -> Path:
    return get_miho_home() / "pixel_documents"


def document_id_for(data: bytes, *, prefix: str = "pde") -> str:
    return f"{prefix}_{hashlib.sha256(data).hexdigest()[:24]}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def document_dir(document_id: str) -> Path:
    clean = "".join(ch for ch in str(document_id) if ch.isalnum() or ch in {"_", "-"})
    if not clean:
        raise ValueError("문서 ID가 비어 있습니다.")
    return pixel_documents_root() / clean


def manifest_path_for(document_id: str) -> Path:
    return document_dir(document_id) / "manifest.json"


def save_manifest(manifest: dict[str, Any]) -> Path:
    document_id = str(manifest.get("document_id") or "").strip()
    if not document_id:
        raise ValueError("문서 ID가 없어 manifest를 저장할 수 없습니다.")
    path = manifest_path_for(document_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_manifest(document_id_or_path: str | Path) -> dict[str, Any]:
    value = Path(str(document_id_or_path)).expanduser()
    path = value if value.exists() else manifest_path_for(str(document_id_or_path))
    if path.is_dir():
        path = path / "manifest.json"
    if not path.exists():
        raise ValueError("문서 근거 manifest를 찾을 수 없습니다.")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("문서 근거 manifest 형식이 올바르지 않습니다.")
    if loaded.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("문서 근거 manifest 버전이 맞지 않습니다.")
    return loaded
