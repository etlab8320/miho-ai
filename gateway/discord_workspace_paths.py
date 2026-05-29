"""Path and manifest helpers for Discord workspace storage."""

from __future__ import annotations

import contextlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home
from utils import atomic_json_write

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]


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


@contextlib.contextmanager
def path_lock(path: Path):
    """Acquire an exclusive cross-process lock for a workspace file.

    Concurrent Discord turns in the same thread can append to the same
    JSONL file at once; without a lock the writes interleave and corrupt a
    line. Uses a sibling ``.lock`` file (POSIX flock / Windows msvcrt) so the
    data file itself stays append-only. Mirrors tools/memory_tool._file_lock.
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None and msvcrt is None:  # pragma: no cover - no locking available
        yield
        return
    fd = open(lock_path, "a+", encoding="utf-8")
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:
            fd.seek(0)
            msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
        yield
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            elif msvcrt is not None:
                fd.seek(0)
                msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        fd.close()


def count_lines(path: Path) -> int:
    """Return the number of lines in a file, or 0 if it cannot be read."""
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def append_jsonl_locked(path: Path, record: dict[str, Any]) -> int:
    """Append one JSON line under an exclusive lock; return the new line count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path_lock(path):
        count = count_lines(path)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return count + 1
