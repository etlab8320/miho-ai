"""Tests for life-record course type persistence."""

from __future__ import annotations

import sqlite3


def test_connect_central_migrates_course_type_column(tmp_path) -> None:
    from plugins.life_record.repository import connect_central

    db = tmp_path / "central.sqlite3"
    raw = sqlite3.connect(db)
    try:
        raw.execute(
            "CREATE TABLE central_grades ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "student_id INTEGER NOT NULL, "
            "grade INTEGER, "
            "semester INTEGER, "
            "category TEXT, "
            "subject TEXT NOT NULL, "
            "credits REAL, "
            "raw_score TEXT, "
            "achievement TEXT, "
            "students_count INTEGER, "
            "rank_grade TEXT, "
            "updated_at TEXT NOT NULL)"
        )
        raw.commit()
    finally:
        raw.close()

    conn = connect_central(db)
    try:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(central_grades)")
        }
    finally:
        conn.close()

    assert "course_type" in columns
