"""SQLite repository helpers for life record data."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from .schema import SCHEMA
from .utils import backup_database, now_iso, safe_name, sha256_file


def db_path(bundle_dir: Path) -> Path:
    return bundle_dir / "life_records.sqlite3"


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_import(
    *,
    bundle_dir: Path,
    pdf_path: Path,
    extracted: Any,
    identity: dict[str, str],
    sections: list[dict[str, Any]],
    attendance_rows: list[dict[str, Any]],
    grade_rows: list[dict[str, Any]],
    note_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    path = db_path(bundle_dir)
    backup_path = backup_database(path, "before_import")
    pdf_hash = sha256_file(pdf_path)
    stored_pdf = _store_pdf(bundle_dir, pdf_path, pdf_hash)
    now = now_iso()
    conn = connect(path)
    try:
        student_id = _upsert_student(conn, identity, now)
        document_id = _upsert_document(conn, student_id, identity, extracted, pdf_path, stored_pdf, pdf_hash, now)
        photo_paths = _replace_photo(conn, bundle_dir, student_id, document_id, identity, extracted.photo, now)
        _replace_sections(conn, document_id, sections, now)
        _replace_attendance(conn, document_id, attendance_rows, now)
        _replace_grades(conn, document_id, grade_rows, now)
        _replace_notes(conn, document_id, note_rows, now)
        summary = {
            "student": identity["name"],
            "pages": extracted.page_count,
            "sections": len(sections),
            "attendance_rows": len(attendance_rows),
            "subject_grade_rows": len(grade_rows),
            "special_note_rows": len(note_rows),
            "photos": len(photo_paths),
            "backup_path": backup_path,
        }
        conn.execute(
            "INSERT INTO extraction_audit_logs(document_id, method, version, result_summary, confidence_before, confidence_after, created_at) VALUES(?,?,?,?,?,?,?)",
            (document_id, "miho_life_record_importer", "0.1.0", json.dumps(summary, ensure_ascii=False), None, _document_confidence(extracted), now),
        )
        conn.commit()
        return {
            **summary,
            "db_path": str(path),
            "student_id": student_id,
            "document_id": document_id,
            "stored_pdf_path": str(stored_pdf),
            "photo_paths": photo_paths,
        }
    finally:
        conn.close()


def latest_document(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT d.*, s.name, s.school_name, s.profile_photo_path FROM student_documents d JOIN students s ON s.id=d.student_id ORDER BY d.id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def document_by_id(path: Path, document_id: int) -> dict[str, Any] | None:
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT d.*, s.name, s.school_name, s.profile_photo_path FROM student_documents d JOIN students s ON s.id=d.student_id WHERE d.id=?",
            (document_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def search_records(path: Path, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    terms = [term for term in query.split() if term]
    conn = connect(path)
    try:
        rows: list[dict[str, Any]] = []
        rows.extend(_search_table(conn, "life_record_sections", "raw_text", terms, limit))
        rows.extend(_search_table(conn, "subject_special_notes", "note_text", terms, limit))
        rows.extend(_search_table(conn, "subject_grades", "raw_row", terms, limit))
        return rows[:limit]
    finally:
        conn.close()


def summary_counts(path: Path, document_id: int) -> dict[str, Any]:
    conn = connect(path)
    try:
        return {
            "sections": _count(conn, "life_record_sections", document_id),
            "attendance_rows": _count(conn, "attendance_records", document_id),
            "subject_grade_rows": _count(conn, "subject_grades", document_id),
            "special_note_rows": _count(conn, "subject_special_notes", document_id),
            "photos": _photo_count(conn, document_id),
        }
    finally:
        conn.close()


def record_verification(path: Path, document_id: int, round_name: str, status: str, summary: dict[str, Any]) -> None:
    conn = connect(path)
    try:
        conn.execute(
            "INSERT INTO verification_runs(document_id, round_name, status, summary_json, created_at) VALUES(?,?,?,?,?)",
            (document_id, round_name, status, json.dumps(summary, ensure_ascii=False), now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def delete_bundle(bundle_dir: Path) -> bool:
    if not bundle_dir.exists():
        return False
    shutil.rmtree(bundle_dir)
    return True


def _store_pdf(bundle_dir: Path, pdf_path: Path, pdf_hash: str) -> Path:
    source_dir = bundle_dir / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    stored = source_dir / f"{pdf_hash[:16]}_original.pdf"
    shutil.copy2(pdf_path, stored)
    return stored


def _upsert_student(conn: sqlite3.Connection, identity: dict[str, str], now: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO students(name, school_name, class_no, student_no, birth_masked, profile_photo_path, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (identity["name"], identity["school_name"], identity["class_no"], identity["student_no"], identity["birth_masked"], None, now, now),
    )
    row = conn.execute(
        "SELECT id FROM students WHERE name=? AND IFNULL(school_name,'')=IFNULL(?, '') AND IFNULL(birth_masked,'')=IFNULL(?, '')",
        (identity["name"], identity["school_name"], identity["birth_masked"]),
    ).fetchone()
    return int(row["id"])


def _upsert_document(conn: sqlite3.Connection, student_id: int, identity: dict[str, str], extracted: Any, pdf_path: Path, stored_pdf: Path, pdf_hash: str, now: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO student_documents(student_id, document_type, source_pdf_path, stored_pdf_path, file_sha256, page_count, issued_at, issuer_school, document_number, verification_number, raw_text, metadata_json, extraction_method, extraction_confidence, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (student_id, "school_life_record", str(pdf_path), str(stored_pdf), pdf_hash, extracted.page_count, identity["issued_at_text"], identity["school_name"], identity["document_number"], identity["verification_number"], extracted.raw_text, json.dumps(extracted.metadata, ensure_ascii=False), "pymupdf_text_layer_v1", _document_confidence(extracted), now),
    )
    row = conn.execute("SELECT id FROM student_documents WHERE file_sha256=?", (pdf_hash,)).fetchone()
    return int(row["id"])


def _replace_photo(conn: sqlite3.Connection, bundle_dir: Path, student_id: int, document_id: int, identity: dict[str, str], photo: Any, now: str) -> list[str]:
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


def _replace_sections(conn: sqlite3.Connection, document_id: int, rows: list[dict[str, Any]], now: str) -> None:
    conn.execute("DELETE FROM life_record_sections WHERE student_document_id=?", (document_id,))
    for row in rows:
        conn.execute(
            "INSERT INTO life_record_sections(student_document_id, section_type, page_start, page_end, raw_text, parsed_json, confidence, review_status, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (document_id, row["section_type"], row["page_start"], row["page_end"], row["raw_text"], row["parsed_json"], row["confidence"], row["review_status"], now),
        )


def _replace_attendance(conn: sqlite3.Connection, document_id: int, rows: list[dict[str, Any]], now: str) -> None:
    conn.execute("DELETE FROM attendance_records WHERE student_document_id=?", (document_id,))
    for row in rows:
        conn.execute(
            "INSERT OR REPLACE INTO attendance_records(student_document_id, grade, school_days, absent_disease, absent_unexcused, absent_other, late_disease, late_unexcused, late_other, early_leave_disease, early_leave_unexcused, early_leave_other, result_disease, result_unexcused, result_other, special_note, confidence, review_status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (document_id, row["grade"], row["school_days"], row["absent_disease"], row["absent_unexcused"], row["absent_other"], row["late_disease"], row["late_unexcused"], row["late_other"], row["early_leave_disease"], row["early_leave_unexcused"], row["early_leave_other"], row["result_disease"], row["result_unexcused"], row["result_other"], row["special_note"], row["confidence"], "needs_review", now),
        )


def _replace_grades(conn: sqlite3.Connection, document_id: int, rows: list[dict[str, Any]], now: str) -> None:
    conn.execute("DELETE FROM subject_grades WHERE student_document_id=?", (document_id,))
    for row in rows:
        conn.execute(
            "INSERT INTO subject_grades(student_document_id, grade, semester, category, subject, credits, raw_score, achievement, students_count, rank_grade, raw_row, confidence, review_status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (document_id, row["grade"], row["semester"], row["category"], row["subject"], row["credits"], row["raw_score"], row["achievement"], row["students_count"], row["rank_grade"], row["raw_row"], row["confidence"], "needs_review", now),
        )


def _replace_notes(conn: sqlite3.Connection, document_id: int, rows: list[dict[str, Any]], now: str) -> None:
    conn.execute("DELETE FROM subject_special_notes WHERE student_document_id=?", (document_id,))
    for row in rows:
        conn.execute(
            "INSERT INTO subject_special_notes(student_document_id, grade, semester, subject, note_text, source_page_start, source_page_end, confidence, review_status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (document_id, row["grade"], row["semester"], row["subject"], row["note_text"], row["source_page_start"], row["source_page_end"], row["confidence"], "needs_review", now),
        )


def _document_confidence(extracted: Any) -> float:
    return 0.94 if extracted.page_texts and min(len(text) for text in extracted.page_texts) > 50 else 0.82


def _count(conn: sqlite3.Connection, table: str, document_id: int) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE student_document_id=?", (document_id,)).fetchone()["n"])


def _photo_count(conn: sqlite3.Connection, document_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM student_photos WHERE document_id=?", (document_id,)).fetchone()["n"])


def _search_table(conn: sqlite3.Connection, table: str, field: str, terms: list[str], limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 200").fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        text = str(row[field] or "")
        if terms and not all(term in text for term in terms):
            continue
        keys = set(row.keys())
        source_page = row["source_page_start"] if "source_page_start" in keys else row["page_start"] if "page_start" in keys else None
        out.append({"table": table, "row_id": row["id"], "snippet": text[:600], "source_page_start": source_page})
        if len(out) >= limit:
            break
    return out
