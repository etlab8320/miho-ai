"""Student record context helpers for hakjong report validation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .hakjong_stage_contract import normalize_student_stage


KST = ZoneInfo("Asia/Seoul")
CENTRAL_LIFE_DB = Path("~/.miho/life_records/central.sqlite3").expanduser()
STAGE_KO = {"grade1": "고1", "grade2": "고2", "grade3": "고3", "graduate": "N수생/졸업"}

FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "영어": ("영어", "영독", "영어권"),
    "국어": ("국어", "문학", "독서", "화법", "작문", "언어"),
    "수학": ("수학", "미적", "확률", "통계", "기하", "대수"),
    "과학": ("과학", "물리", "화학", "생명", "지구", "융합"),
    "사회": ("사회", "지리", "역사", "한국사", "세계사", "정치", "법", "경제", "윤리", "사상", "문화", "탐구"),
    "체육": ("체육", "운동", "스포츠"),
    "예술": ("음악", "미술", "연주", "창작", "감상", "디자인", "연극"),
    "기타": ("기술", "가정", "정보", "한문", "중국어", "일본어", "외국어", "교양", "진로", "보건"),
}


def field_of(subject: str) -> str:
    text = str(subject or "")
    if text.startswith("창체") or text.startswith("창의적"):
        return "창체"
    for field, keywords in FIELD_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return field
    return "기타"


def student_record_brief(student_name: str) -> dict[str, list[str]]:
    if not CENTRAL_LIFE_DB.exists():
        return {}
    import sqlite3

    by_field: dict[str, list[str]] = {}
    with sqlite3.connect(CENTRAL_LIFE_DB) as db:
        row = db.execute(
            "SELECT id FROM students WHERE name = ? OR name LIKE ? LIMIT 1",
            (student_name, f"%{student_name}%"),
        ).fetchone()
        if not row:
            return {}
        for grade, subject, text in db.execute(
            "SELECT grade, subject, note_text FROM central_notes WHERE student_id = ? ORDER BY grade",
            (row[0],),
        ):
            if not text or not str(text).strip():
                continue
            full = " ".join(str(text).split())
            by_field.setdefault(field_of(subject), []).append(f"{grade}학년 {subject}: {full}")
    return by_field


def record_brief_text(brief: dict[str, list[str]], **_: Any) -> str:
    chunks: list[str] = []
    for field, items in brief.items():
        sample = "; ".join(item[:80] for item in items[:2])
        chunks.append(f"[{field}] {sample}")
    return " / ".join(chunks)


def content_text(content: Any) -> str:
    parts: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, str):
            parts.append(obj)
        elif isinstance(obj, dict):
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(content)
    return " ".join(parts)


def stage_grade(student_stage: str) -> int | None:
    norm = normalize_student_stage(student_stage)
    grade = {"grade1": 1, "grade2": 2, "grade3": 3}.get(norm)
    if grade or norm == "graduate":
        return grade
    compact = str(student_stage or "").replace(" ", "")
    for value in (1, 2, 3):
        if f"{value}학년" in compact:
            return value
    return None


def completed_record_rewrite_phrase(text: str) -> str | None:
    marker = "세특"
    rewrite_words = ("정리하", "재구성", "재정렬", "채워", "채우", "설계", "디벨롭", "보강", "발전시키", "만들")
    start = str(text or "").find(marker)
    while start >= 0:
        window = str(text or "")[start : start + 60]
        if any(word in window for word in rewrite_words):
            return window
        start = str(text or "").find(marker, start + len(marker))
    return None


def infer_stage_from_birth(student_name: str) -> str | None:
    if not CENTRAL_LIFE_DB.exists():
        return None
    import sqlite3

    with sqlite3.connect(CENTRAL_LIFE_DB) as db:
        row = db.execute(
            "SELECT birth_masked FROM students WHERE name = ? OR name LIKE ? LIMIT 1",
            (student_name, f"%{student_name}%"),
        ).fetchone()
    if not row or not row[0]:
        return None
    digits = "".join(ch for ch in str(row[0]) if ch.isdigit())
    if len(digits) < 4:
        return None
    birth_year = 2000 + int(digits[:2])
    month = int(digits[2:4])

    now = datetime.now(KST)
    school_year = now.year if now.month >= 3 else now.year - 1
    cohort_year = birth_year if month >= 3 else birth_year - 1
    delta = (school_year - 18) - cohort_year
    if delta >= 1:
        return "graduate"
    return {0: "grade3", -1: "grade2", -2: "grade1"}.get(delta)
