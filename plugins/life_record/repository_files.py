"""File persistence helpers for life-record repository."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

from .utils import safe_name


def store_source_document(bundle_dir: Path, source_path: Path, document_hash: str) -> Path:
    source_dir = bundle_dir / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    stored = source_dir / f"{document_hash[:16]}_original{source_path.suffix or '.pdf'}"
    if source_path.resolve() != stored.resolve():
        shutil.copy2(source_path, stored)
    return stored


def replace_photo(
    conn: sqlite3.Connection,
    bundle_dir: Path,
    student_id: int,
    document_id: int,
    identity: dict[str, str],
    photo: Any,
    now: str,
) -> list[str]:
    conn.execute("DELETE FROM student_photos WHERE document_id=?", (document_id,))
    if not photo:
        return []
    photo_dir = bundle_dir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    path = photo_dir / f"{safe_name(identity['name'])}_profile_p{photo.source_page}.{photo.ext}"
    path.write_bytes(photo.image_bytes)
    conn.execute(
        "INSERT INTO student_photos(student_id, document_id, image_path, source_page, width, height, image_sha256, is_primary, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (student_id, document_id, str(path), photo.source_page, photo.width, photo.height, photo.sha256, 1, now),
    )
    conn.execute("UPDATE students SET profile_photo_path=?, updated_at=? WHERE id=?", (str(path), now, student_id))
    return [str(path)]
