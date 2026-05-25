"""Path and manifest helpers for Discord workspace storage."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home
from utils import atomic_json_write


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def clean_component(value: Any, fallback: str) -> str:
    raw = str(value or "").strip() or fallback
    raw = re.sub(r"\s+", "-", raw.lower())
    raw = re.sub(r"[^a-z0-9_.-]+", "-", raw)
    raw = raw.strip(".-")
    return raw[:64] or fallback


def named_id(name: Any, ident: Any, fallback: str) -> str:
    clean_name = clean_component(name, fallback)
    clean_id = clean_component(ident, "unknown")
    return f"{clean_name}__{clean_id}"


def workspace_child(parent: Path, name: Any, ident: Any, fallback: str) -> Path:
    wanted = named_id(name, ident, fallback)
    suffix = "__" + clean_component(ident, "unknown")
    if parent.exists():
        for child in parent.iterdir():
            if child.is_dir() and child.name.endswith(suffix):
                return child
    return parent / wanted


def child_by_id(parent: Path, ident: Any) -> Path | None:
    suffix = "__" + clean_component(ident, "unknown")
    if not parent.exists():
        return None
    for child in parent.iterdir():
        if child.is_dir() and child.name.endswith(suffix):
            return child
    return None


def write_manifest(path: Path, data: dict[str, Any]) -> None:
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            existing = {}
    now = utc_now()
    merged = {
        **existing,
        **{k: v for k, v in data.items() if v not in (None, "")},
        "updated_at": now,
    }
    if "created_at" not in merged:
        merged["created_at"] = now
    atomic_json_write(path, merged, indent=2)


def discord_root() -> Path:
    return get_miho_home() / "discord"
