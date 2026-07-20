"""Student record loading helpers for Susi calculations."""

from __future__ import annotations

import json
import re
import sqlite3
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home
from plugins.life_record.student_aliases import normalize_student_alias


CENTRAL_LIFE_DB = get_miho_home() / "life_records" / "central.sqlite3"


class StudentResolutionStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


_LAST_RESOLUTION_STATUS: ContextVar[StudentResolutionStatus | None] = ContextVar(
    "susi_last_student_resolution_status",
    default=None,
)


@dataclass(frozen=True)
class StudentGradeLookup:
    status: StudentResolutionStatus
    student_id: int | None = None
    student_name: str | None = None
    grades: tuple[dict[str, Any], ...] = ()


def parse_raw_score(value: Any) -> tuple[float | None, float | None, float | None]:
    """Parse 생기부 raw score cells.

    Accepted forms:
    - '81/89.6(13.3)' -> (raw, mean, std)
    - '84/82.6'       -> (raw, mean, None)  # career subjects often omit std
    - '81'            -> (raw, None, None)
    """
    text = str(value or "").strip()
    if not text:
        return None, None, None
    full = re.match(
        r"\s*([\d.]+)\s*/\s*([\d.]+)\s*\(\s*([\d.]+)\s*\)",
        text,
    )
    if full:
        try:
            return float(full.group(1)), float(full.group(2)), float(full.group(3))
        except ValueError:
            return None, None, None
    pair = re.match(r"\s*([\d.]+)\s*/\s*([\d.]+)\s*$", text)
    if pair:
        try:
            return float(pair.group(1)), float(pair.group(2)), None
        except ValueError:
            return None, None, None
    solo = re.match(r"\s*([\d.]+)\s*$", text)
    if solo:
        try:
            return float(solo.group(1)), None, None
        except ValueError:
            return None, None, None
    return None, None, None


def parse_achievement(value: Any) -> str | None:
    """Normalize achievement cells: 'A(302)' / 'B' / '우수' -> 'A'/'B'/'우수'."""
    text = str(value or "").strip()
    if not text:
        return None
    # Strip parenthetical enrollment counts: A(178), B(81)
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    return text or None


def lookup_student_grades(
    student_query: str,
    *,
    student_id: int | None = None,
    source_thread: str = "",
    database: Path | None = None,
) -> StudentGradeLookup:
    database_path = database or CENTRAL_LIFE_DB
    if not database_path.exists():
        return _resolution(StudentResolutionStatus.NOT_FOUND)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    try:
        resolution = _resolve_student(
            conn,
            query=student_query,
            student_id=student_id,
            source_thread=source_thread,
        )
        if resolution.status is not StudentResolutionStatus.FOUND:
            return _resolution(resolution.status)
        rows = conn.execute(
            """
            SELECT grade, semester, category, subject, credits, rank_grade, achievement,
                   raw_score, students_count, course_type
              FROM central_grades
             WHERE student_id = ?
            """,
            (resolution.student_id,),
        ).fetchall()
        grades = tuple(_grade_row_from_central(row) for row in rows)
        grades = _with_achievement_ratios(conn, resolution.student_id, grades)
        return _resolution(
            StudentResolutionStatus.FOUND,
            student_id=resolution.student_id,
            student_name=resolution.student_name,
            grades=grades,
        )
    finally:
        conn.close()


def student_grades_from_central(
    student_query: str,
    *,
    student_id: int | None = None,
    source_thread: str | None = None,
    database: Path | None = None,
) -> tuple[str | None, list[dict[str, Any]]]:
    result = lookup_student_grades(
        student_query,
        student_id=student_id,
        source_thread=_current_source_thread() if source_thread is None else source_thread,
        database=database,
    )
    return result.student_name, list(result.grades)


def last_student_resolution_status() -> StudentResolutionStatus:
    return _LAST_RESOLUTION_STATUS.get() or StudentResolutionStatus.NOT_FOUND


def _resolve_student(
    conn: sqlite3.Connection,
    *,
    query: str,
    student_id: int | None,
    source_thread: str,
) -> StudentGradeLookup:
    students = _student_rows(conn)
    if student_id is not None:
        return _one_student(
            [student for student in students if int(student["id"]) == student_id]
        )

    normalized_query = normalize_student_identity(query)
    if normalized_query:
        exact = [
            student
            for student in students
            if normalize_student_identity(student["name"]) == normalized_query
        ]
        exact = _prefer_thread(exact, source_thread)
        if exact:
            return _one_student(exact)
        alias_students = _alias_students(
            conn,
            normalized_alias=normalized_query,
            source_thread=source_thread,
        )
        if alias_students:
            return _one_student(alias_students)
        return StudentGradeLookup(StudentResolutionStatus.NOT_FOUND)

    if source_thread:
        bound = [
            student
            for student in students
            if str(student["source_thread"] or "").strip() == source_thread.strip()
        ]
        return _one_student(bound)
    return StudentGradeLookup(StudentResolutionStatus.NOT_FOUND)


def normalize_student_identity(value: object) -> str:
    return normalize_student_alias(value)


def _student_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(students)").fetchall()
    }
    source = "source_thread" if "source_thread" in columns else "'' AS source_thread"
    return conn.execute(
        f"SELECT id, name, {source} FROM students ORDER BY id"  # noqa: S608
    ).fetchall()


def _alias_students(
    conn: sqlite3.Connection,
    *,
    normalized_alias: str,
    source_thread: str,
) -> list[sqlite3.Row]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='student_aliases'"
    ).fetchone()
    if exists is None:
        return []
    rows = conn.execute(
        """
        SELECT s.id, s.name, COALESCE(s.source_thread, '') AS source_thread,
               COALESCE(a.source_thread, '') AS alias_thread
          FROM student_aliases a
          JOIN students s ON s.id = a.student_id
         WHERE a.alias_normalized = ?
         ORDER BY s.id
        """,
        (normalized_alias,),
    ).fetchall()
    if source_thread:
        scoped = [row for row in rows if row["alias_thread"] == source_thread]
        if scoped:
            return scoped
    return [row for row in rows if not str(row["alias_thread"] or "").strip()]


def _prefer_thread(students: list[sqlite3.Row], source_thread: str) -> list[sqlite3.Row]:
    if len(students) <= 1 or not source_thread:
        return students
    scoped = [
        student
        for student in students
        if str(student["source_thread"] or "").strip() == source_thread.strip()
    ]
    return scoped or students


def _one_student(students: list[sqlite3.Row]) -> StudentGradeLookup:
    unique = {int(student["id"]): student for student in students}
    if not unique:
        return StudentGradeLookup(StudentResolutionStatus.NOT_FOUND)
    if len(unique) > 1:
        return StudentGradeLookup(StudentResolutionStatus.AMBIGUOUS)
    student = next(iter(unique.values()))
    return StudentGradeLookup(
        StudentResolutionStatus.FOUND,
        student_id=int(student["id"]),
        student_name=str(student["name"]),
    )


def _resolution(
    status: StudentResolutionStatus,
    *,
    student_id: int | None = None,
    student_name: str | None = None,
    grades: tuple[dict[str, Any], ...] = (),
) -> StudentGradeLookup:
    _LAST_RESOLUTION_STATUS.set(status)
    return StudentGradeLookup(status, student_id, student_name, grades)


def _current_source_thread() -> str:
    try:
        from plugins.life_record.context import THREAD_ID

        return str(THREAD_ID.get() or "").strip()
    except (ImportError, LookupError):
        return ""


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
        "성취도": parse_achievement(row["achievement"]),
        "원점수": raw_score,
        "평균": mean_score,
        "표준편차": standard_deviation,
        "재적수": row["students_count"],
        "과목구분": course_type,
        "course_type": course_type,
    }


def _with_achievement_ratios(
    conn: sqlite3.Connection,
    student_id: int | None,
    grades: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    if student_id is None or not _table_exists(conn, "central_achievement_ratios"):
        return grades
    rows = conn.execute(
        """
        SELECT grade, semester, subject, ratios_json
          FROM central_achievement_ratios
         WHERE student_id = ?
        """,
        (student_id,),
    ).fetchall()
    ratios_by_key: dict[tuple[int | None, int | None, str], dict[str, float]] = {}
    for row in rows:
        try:
            parsed = json.loads(str(row["ratios_json"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue
        ratios_by_key[(int(row["grade"]), int(row["semester"]), str(row["subject"]))] = {
            str(key): float(value)
            for key, value in parsed.items()
            if _is_number(value)
        }
    enriched: list[dict[str, Any]] = []
    for grade in grades:
        item = dict(grade)
        key = (
            _int_or_none(item.get("학년")),
            _int_or_none(item.get("학기")),
            str(item.get("과목") or "").strip(),
        )
        if ratios := ratios_by_key.get(key):
            item["achievement_ratios"] = ratios
            item["성취도별비율"] = json.dumps(ratios, ensure_ascii=False, sort_keys=True)
        enriched.append(item)
    return tuple(enriched)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


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
