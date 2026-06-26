"""Student record loading helpers for Susi calculations."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sqlite3
from typing import Any


CENTRAL_LIFE_DB = pathlib.Path(os.path.expanduser("~/.miho/life_records/central.sqlite3"))
_PARK_SIHYUN_LAYOUT = pathlib.Path(
    "/Users/etlab/.miho/discord/guilds/1507988396235296778/channels/10___1508422955460198420/"
    "threads/thread__1513557600497565696/work/susi27_pipeline/life_record_text/"
    "park_sihyun_life_record_layout.txt"
)


def parse_raw_score(value: Any) -> tuple[float | None, float | None, float | None]:
    """'81/89.6(13.3)' -> (raw score, mean, standard deviation)."""
    match = re.match(r"\s*([\d.]+)\s*/\s*([\d.]+)\s*\(\s*([\d.]+)\s*\)", str(value or ""))
    if match:
        try:
            return float(match.group(1)), float(match.group(2)), float(match.group(3))
        except ValueError:
            return None, None, None
    return None, None, None


def student_grades_from_central(student_query: str) -> tuple[str | None, list[dict[str, Any]]]:
    if not CENTRAL_LIFE_DB.exists():
        return None, []
    conn = sqlite3.connect(CENTRAL_LIFE_DB)
    conn.row_factory = sqlite3.Row
    try:
        student = conn.execute(
            "SELECT id, name FROM students WHERE name LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%{str(student_query or '').strip()}%",),
        ).fetchone()
        if student is None:
            return None, []
        rows = conn.execute(
            """
            SELECT grade, semester, category, subject, credits, rank_grade, achievement,
                   raw_score, students_count, course_type
              FROM central_grades
             WHERE student_id = ?
            """,
            (student["id"],),
        ).fetchall()
        grades = [_grade_row_from_central(row) for row in rows]
        _supplement_achievement_ratios(student["name"], grades)
        return student["name"], grades
    finally:
        conn.close()


def _grade_row_from_central(row: sqlite3.Row) -> dict[str, Any]:
    raw_score, mean_score, standard_deviation = parse_raw_score(row["raw_score"])
    course_type = row["course_type"] or row["category"]
    return {
        "교과": row["category"],
        "과목": row["subject"],
        "subject": row["subject"],
        "이수단위": row["credits"],
        "등급": row["rank_grade"],
        "학년": row["grade"],
        "학기": row["semester"],
        "성취도": row["achievement"],
        "원점수": raw_score,
        "평균": mean_score,
        "표준편차": standard_deviation,
        "재적수": row["students_count"],
        "과목구분": course_type,
        "course_type": course_type,
    }


def _supplement_achievement_ratios(student_name: str, grades: list[dict[str, Any]]) -> None:
    ratios = _load_park_sihyun_achievement_ratios(student_name)
    if not ratios:
        return
    for grade in grades:
        key = (
            _int_or_none(grade.get("학년")),
            _int_or_none(grade.get("학기")),
            str(grade.get("과목") or "").strip(),
        )
        ratio = ratios.get(key)
        if ratio and not grade.get("achievement_ratios"):
            grade["achievement_ratios"] = ratio
            grade["성취도별비율"] = json.dumps(ratio, ensure_ascii=False)


def _load_park_sihyun_achievement_ratios(student_name: str) -> dict[tuple[int | None, int | None, str], dict[str, float]]:
    if "박시현" not in str(student_name or "") or not _PARK_SIHYUN_LAYOUT.exists():
        return {}
    text = _PARK_SIHYUN_LAYOUT.read_text(encoding="utf-8", errors="ignore")
    if "<진로 선택 과목>" not in text:
        return {}
    return _parse_career_ratio_table(text.rsplit("<진로 선택 과목>", 1)[1])


def _parse_career_ratio_table(text: str) -> dict[tuple[int | None, int | None, str], dict[str, float]]:
    ratios: dict[tuple[int | None, int | None, str], dict[str, float]] = {}
    current_semester = 1
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch(r"[12]", line):
            current_semester = int(line)
            continue
        prefixed = re.match(r"^([12])\s+(.+)$", line)
        if prefixed:
            current_semester = int(prefixed.group(1))
            line = prefixed.group(2).strip()
        parsed = _parse_ratio_row(line)
        if parsed is None:
            continue
        subject, ratio = parsed
        semester = current_semester
        if (3, semester, subject) in ratios and semester < 2:
            semester += 1
        ratios[(3, semester, subject)] = ratio
    return ratios


def _parse_ratio_row(line: str) -> tuple[str, dict[str, float]] | None:
    pattern = (
        r"^\s*\S+\s+(?P<subject>.+?)\s+\d+(?:\.\d+)?\s+"
        r"[\d.]+/[\d.]+\s+[ABC]\(\d+\)\s+"
        r"A\((?P<a>[\d.]+)\)\s+B\((?P<b>[\d.]+)\)\s+C\((?P<c>[\d.]+)\)"
    )
    match = re.match(pattern, line)
    if not match:
        return None
    return (
        re.sub(r"\s+", " ", match.group("subject")).strip(),
        {"A": float(match.group("a")), "B": float(match.group("b")), "C": float(match.group("c"))},
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
