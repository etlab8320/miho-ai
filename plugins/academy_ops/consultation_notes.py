"""Local academy consultation-note storage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from miho_constants import get_miho_home


KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class ConsultationNote:
    id: int
    discord_user_id: str
    academy_id: str
    paca_student_id: int
    student_name: str
    note: str
    consulted_at: str
    created_at: str

    def to_public_dict(self) -> dict[str, str]:
        payload = asdict(self)
        return {key: str(value) for key, value in payload.items()}


class ConsultationNoteRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or get_miho_home() / "academy_ops" / "consultation_notes.sqlite3"

    def add_note(
        self,
        *,
        discord_user_id: str,
        academy_id: str,
        paca_student_id: int,
        student_name: str,
        note: str,
        consulted_at: str | None = None,
    ) -> ConsultationNote:
        clean_note = _clean_note(note)
        if not clean_note:
            raise ValueError("저장할 상담 내용을 알려줘.")
        now = _now_iso()
        day = _clean_day(consulted_at) or now[:10]
        self._ensure_schema()
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO consultation_notes (
                    discord_user_id, academy_id, paca_student_id, student_name,
                    note, consulted_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(discord_user_id),
                    str(academy_id),
                    int(paca_student_id),
                    str(student_name),
                    clean_note,
                    day,
                    now,
                ),
            )
            note_id = int(cursor.lastrowid)
        return ConsultationNote(
            note_id,
            str(discord_user_id),
            str(academy_id),
            int(paca_student_id),
            str(student_name),
            clean_note,
            day,
            now,
        )

    def recent_notes(self, *, academy_id: str, paca_student_id: int, limit: int = 3) -> list[dict[str, str]]:
        self._ensure_schema()
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, discord_user_id, academy_id, paca_student_id, student_name,
                       note, consulted_at, created_at
                FROM consultation_notes
                WHERE academy_id = ? AND paca_student_id = ?
                ORDER BY consulted_at DESC, id DESC
                LIMIT ?
                """,
                (str(academy_id), int(paca_student_id), max(1, min(int(limit), 10))),
            ).fetchall()
        return [dict(row) for row in rows]

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS consultation_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_user_id TEXT NOT NULL,
                    academy_id TEXT NOT NULL,
                    paca_student_id INTEGER NOT NULL,
                    student_name TEXT NOT NULL,
                    note TEXT NOT NULL,
                    consulted_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_consultation_notes_student
                ON consultation_notes (academy_id, paca_student_id, consulted_at DESC, id DESC)
                """
            )


def _clean_note(note: str) -> str:
    return " ".join(str(note or "").split())[:600]


def _clean_day(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date().isoformat()
    except ValueError:
        return None


def _now_iso() -> str:
    return datetime.now(KST).replace(microsecond=0).isoformat()
