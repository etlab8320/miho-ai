"""Small helpers for life record ingestion."""

from __future__ import annotations

import hashlib
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(value: Any, fallback: str = "student") -> str:
    clean = re.sub(r"[^가-힣A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return clean.strip("._")[:80] or fallback


def clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm(value: Any) -> str:
    return re.sub(r"\s+", "", "" if value is None else str(value))


def backup_database(db_path: Path, reason: str, keep: int = 30) -> str | None:
    if not db_path.exists():
        return None
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = backup_dir / f"{db_path.stem}_{stamp}_{safe_name(reason, 'backup')}.sqlite3"
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(out))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    backups = sorted(backup_dir.glob(f"{db_path.stem}_*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[keep:]:
        old.unlink(missing_ok=True)
    return str(out)


def replace_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
