"""Explicit aliases for confirmed central student identities."""

from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from .repository import connect_central
from .utils import now_iso


def normalize_student_alias(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(normalized.casefold().split())


def save_student_alias(
    student_id: int,
    alias: str,
    *,
    source_thread: str = "",
    central_path: Path | None = None,
) -> dict[str, Any]:
    """Persist an operator-confirmed alias without inferring identity."""

    normalized = normalize_student_alias(alias)
    if not normalized:
        raise ValueError("학생 별칭이 비어 있어 저장할 수 없어.")
    conn = connect_central(central_path)
    try:
        student = conn.execute(
            "SELECT id, name FROM students WHERE id = ?",
            (int(student_id),),
        ).fetchone()
        if student is None:
            raise ValueError("별칭을 연결할 학생을 찾지 못했어.")
        thread = str(source_thread or "").strip()
        try:
            conn.execute(
                """
                INSERT INTO student_aliases(
                    student_id, alias, alias_normalized, source_thread, confirmed_at
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (int(student_id), str(alias).strip(), normalized, thread, now_iso()),
            )
        except sqlite3.IntegrityError:
            conn.execute(
                """
                UPDATE student_aliases
                   SET alias = ?, confirmed_at = ?
                 WHERE student_id = ? AND alias_normalized = ? AND source_thread = ?
                """,
                (str(alias).strip(), now_iso(), int(student_id), normalized, thread),
            )
        conn.commit()
        return {
            "student_id": int(student["id"]),
            "student_name": str(student["name"]),
            "alias": str(alias).strip(),
            "source_thread": thread,
        }
    finally:
        conn.close()


__all__ = ["normalize_student_alias", "save_student_alias"]
