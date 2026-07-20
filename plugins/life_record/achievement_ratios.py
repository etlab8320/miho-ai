"""Confirmed achievement-ratio metadata for central student grades."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .repository import connect_central
from .utils import now_iso


def save_achievement_ratios(
    student_id: int,
    *,
    grade: int,
    semester: int,
    subject: str,
    ratios: dict[str, Any],
    central_path: Path | None = None,
) -> None:
    clean_ratios = {
        str(key): float(value)
        for key, value in ratios.items()
        if str(key).strip() and _is_number(value)
    }
    if not clean_ratios:
        raise ValueError("저장할 성취도 비율이 없어.")
    conn = connect_central(central_path)
    try:
        if conn.execute("SELECT 1 FROM students WHERE id = ?", (int(student_id),)).fetchone() is None:
            raise ValueError("성취도 비율을 연결할 학생을 찾지 못했어.")
        conn.execute(
            """
            INSERT INTO central_achievement_ratios(
                student_id, grade, semester, subject, ratios_json, confirmed_at
            ) VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(student_id, grade, semester, subject) DO UPDATE SET
                ratios_json = excluded.ratios_json,
                confirmed_at = excluded.confirmed_at
            """,
            (
                int(student_id),
                int(grade),
                int(semester),
                str(subject).strip(),
                json.dumps(clean_ratios, ensure_ascii=False, sort_keys=True),
                now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


__all__ = ["save_achievement_ratios"]
