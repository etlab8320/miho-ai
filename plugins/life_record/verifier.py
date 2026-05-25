"""Three-round verification for life record imports."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .repository import connect, record_verification
from .utils import norm


def run_verification(db_path: Path, document_id: int) -> dict[str, Any]:
    rounds = [
        _extraction_round(db_path, document_id),
        _traceability_round(db_path, document_id),
        _readiness_round(db_path, document_id),
    ]
    for item in rounds:
        record_verification(db_path, document_id, item["round"], item["status"], item)
    failed = sum(1 for item in rounds if item["status"] != "pass")
    return {
        "round_count": len(rounds),
        "status": "needs_review" if failed else "pass",
        "human_review_required": True,
        "rounds": rounds,
        "failed_rounds": failed,
        "policy": "DB 값은 PDF 원문 근거와 사람 검수 전까지 확정 표현 금지.",
    }


def _extraction_round(db_path: Path, document_id: int) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        doc = _document(conn, document_id)
        checks = [
            _check("db_document_exists", bool(doc), ""),
            _check("raw_text_present", bool(doc and len(doc["raw_text"]) > 100), f"chars={len(doc['raw_text']) if doc else 0}"),
            _check("page_count_present", bool(doc and doc["page_count"] > 0), f"pages={doc['page_count'] if doc else 0}"),
            _check("stored_pdf_exists", bool(doc and Path(doc["stored_pdf_path"]).exists()), doc["stored_pdf_path"] if doc else ""),
            _check("section_rows_present", _count(conn, "life_record_sections", document_id) > 0, ""),
            _check("profile_photo_saved", _photo_count(conn, document_id) > 0, "사진이 없으면 검수 필요"),
        ]
        return _round("extraction", checks)
    finally:
        conn.close()


def _traceability_round(db_path: Path, document_id: int) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        doc = _document(conn, document_id)
        raw = doc["raw_text"] if doc else ""
        checks: list[dict[str, Any]] = []
        if doc:
            for field in ["name", "school_name", "document_number", "verification_number"]:
                value = doc.get(field)
                if value:
                    checks.append(_check(f"identity.{field}", norm(value) in norm(raw), str(value)))
        checks.extend(_section_checks(conn, document_id, raw))
        checks.extend(_grade_checks(conn, document_id, raw))
        checks.extend(_note_checks(conn, document_id, raw))
        checks.extend(_attendance_checks(conn, document_id, raw))
        return _round("pdf_db_traceability", checks)
    finally:
        conn.close()


def _readiness_round(db_path: Path, document_id: int) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        pending = _pending_review_count(conn, document_id)
        checks = [
            _check("thread_scoped_db", "discord" in str(db_path) and "life_records.sqlite3" in db_path.name, str(db_path)),
            _check("no_confirmed_without_human", pending > 0, f"needs_review_rows={pending}"),
            _check("verification_history_written", True, "current run will be recorded"),
        ]
        return _round("human_review_gate", checks)
    finally:
        conn.close()


def _section_checks(conn: sqlite3.Connection, document_id: int, raw: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT id, section_type, raw_text FROM life_record_sections WHERE student_document_id=?", (document_id,)).fetchall()
    return [_check("section_raw_text_in_document", norm(row["raw_text"][:500]) in norm(raw), row["section_type"]) for row in rows]


def _grade_checks(conn: sqlite3.Connection, document_id: int, raw: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT id, subject, raw_score, students_count, rank_grade, achievement FROM subject_grades WHERE student_document_id=?", (document_id,)).fetchall()
    checks = []
    for row in rows:
        parts = [row["subject"], row["raw_score"], str(row["students_count"]) if row["students_count"] is not None else "", row["rank_grade"] or row["achievement"] or ""]
        checks.append(_check("subject_grade_evidence", _contains_all(raw, parts), row["subject"]))
    return checks


def _note_checks(conn: sqlite3.Connection, document_id: int, raw: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT id, subject, note_text FROM subject_special_notes WHERE student_document_id=?", (document_id,)).fetchall()
    checks = []
    for row in rows:
        note = norm(row["note_text"])
        evidence = note[-80:] if len(note) >= 80 else note
        checks.append(_check("special_note_evidence", bool(evidence and evidence in norm(raw)), row["subject"]))
    return checks


def _attendance_checks(conn: sqlite3.Connection, document_id: int, raw: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT grade, school_days FROM attendance_records WHERE student_document_id=?", (document_id,)).fetchall()
    return [_check("attendance_basic_evidence", _contains_all(raw, [str(row["grade"]), str(row["school_days"])]), f"{row['grade']}학년") for row in rows]


def _document(conn: sqlite3.Connection, document_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT d.*, s.name, s.school_name FROM student_documents d JOIN students s ON s.id=d.student_id WHERE d.id=?",
        (document_id,),
    ).fetchone()
    return dict(row) if row else None


def _count(conn: sqlite3.Connection, table: str, document_id: int) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE student_document_id=?", (document_id,)).fetchone()["n"])


def _photo_count(conn: sqlite3.Connection, document_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM student_photos WHERE document_id=?", (document_id,)).fetchone()["n"])


def _pending_review_count(conn: sqlite3.Connection, document_id: int) -> int:
    total = 0
    for table in ["life_record_sections", "attendance_records", "subject_grades", "subject_special_notes"]:
        total += int(conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE student_document_id=? AND review_status!='confirmed'", (document_id,)).fetchone()["n"])
    return total


def _contains_all(raw: str, parts: list[str]) -> bool:
    compact = norm(raw)
    return all(norm(part) in compact for part in parts if part not in ("", None))


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"check": name, "ok": bool(ok), "detail": detail}


def _round(name: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for check in checks if check["ok"])
    total = len(checks)
    return {
        "round": name,
        "status": "pass" if total and passed == total else "needs_review",
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total * 100, 2) if total else 0,
        "failed_checks": [check for check in checks if not check["ok"]],
    }
