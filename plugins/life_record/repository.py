"""SQLite repository for life record data — vision/consensus based.

Thread bundle DB holds one document's extraction (with per-row review_status from
consensus). Confirmed data is promoted into the central student DB, accumulated per
student across semesters (1학년 → 2·3학년).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home

from .consensus import CONFIRMED
from .repository_files import replace_photo, store_source_document
from .repository_rows import (
    clear_central_student_rows,
    delete_central_duplicate_students,
    delete_superseded_mhtml_documents,
    replace_attendance,
    replace_sections,
)
from .schema import CENTRAL_SCHEMA, SCHEMA
from .utils import backup_database, now_iso, sha256_file


def db_path(bundle_dir: Path) -> Path:
    return bundle_dir / "life_records.sqlite3"


def central_db_path() -> Path:
    path = get_miho_home() / "life_records" / "central.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def connect_central(path: Path | None = None) -> sqlite3.Connection:
    path = path or central_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(CENTRAL_SCHEMA)
    return conn


# ---------------------------------------------------------------- consensus helpers

def identity_from_consensus(consensus: dict[str, Any]) -> dict[str, str]:
    ident = consensus.get("identity") or {}

    def value(field: str) -> str | None:
        info = ident.get(field) or {}
        return info.get("value")

    birth6 = value("birth6")
    return {
        "name": value("name") or "미상",
        "school_name": value("school_name") or "",
        "class_no": value("class_no") or "",
        "student_no": value("student_no") or "",
        "birth_masked": f"{birth6}-*******" if birth6 else "",
    }


def _row_status(row: dict[str, Any]) -> str:
    return CONFIRMED if row.get("_status") == CONFIRMED else "needs_review"


def _row_conf(row: dict[str, Any]) -> float:
    try:
        return float(row.get("_confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------- bundle import

def save_import(
    *,
    bundle_dir: Path,
    pdf_path: Path,
    page_count: int,
    raw_text: str,
    metadata: dict[str, Any],
    consensus: dict[str, Any],
    photo: Any = None,
    extraction_method: str = "codex_vision_gpt5.5_v1",
    source_thread: str = "",
    document_path: Path | None = None,
    stored_document_path: Path | None = None,
    document_type: str = "school_life_record",
    sections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    path = db_path(bundle_dir)
    backup_path = backup_database(path, "before_import")
    source_path = document_path or pdf_path
    document_hash = sha256_file(source_path)
    stored_document = stored_document_path or store_source_document(bundle_dir, source_path, document_hash)
    identity = identity_from_consensus(consensus)
    now = now_iso()
    conn = connect(path)
    try:
        student_id = _upsert_student(conn, identity, now)
        document_id = _upsert_document(conn, student_id, identity, page_count, raw_text, metadata, source_path, stored_document, document_hash, extraction_method, _doc_confidence(consensus), now, document_type)
        photo_paths = replace_photo(conn, bundle_dir, student_id, document_id, identity, photo, now)
        _replace_grades(conn, document_id, consensus.get("grades") or [], now)
        _replace_notes(conn, document_id, consensus.get("notes") or [], now)
        replace_attendance(conn, document_id, consensus.get("attendance") or [], now)
        _replace_awards(conn, document_id, consensus.get("awards") or [], now)
        replace_sections(conn, document_id, sections or [], now)
        removed_documents = delete_superseded_mhtml_documents(conn, student_id, document_id) if document_type == "life_record_mhtml" else 0
        summary = {
            "student": identity["name"],
            "pages": page_count,
            "subject_grade_rows": len(consensus.get("grades") or []),
            "special_note_rows": len(consensus.get("notes") or []),
            "attendance_rows": len(consensus.get("attendance") or []),
            "award_rows": len(consensus.get("awards") or []),
            "section_rows": len(sections or []),
            "superseded_documents": removed_documents,
            "photos": len(photo_paths),
            "backup_path": backup_path,
        }
        conn.execute(
            "INSERT INTO extraction_audit_logs(document_id, method, version, result_summary, confidence_before, confidence_after, created_at) VALUES(?,?,?,?,?,?,?)",
            (document_id, extraction_method, "1.0.0", json.dumps(summary, ensure_ascii=False), None, _doc_confidence(consensus), now),
        )
        conn.commit()
        return {
            **summary,
            "db_path": str(path),
            "student_id": student_id,
            "document_id": document_id,
            "stored_pdf_path": str(stored_document),
            "photo_paths": photo_paths,
            "source_thread": source_thread,
        }
    finally:
        conn.close()


def _doc_confidence(consensus: dict[str, Any]) -> float:
    ident = consensus.get("identity") or {}
    confs = [info.get("confidence", 0.0) for info in ident.values() if info.get("value")]
    return round(sum(confs) / len(confs), 2) if confs else 0.5


def _upsert_student(conn: sqlite3.Connection, identity: dict[str, str], now: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO students(name, school_name, class_no, student_no, birth_masked, profile_photo_path, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (identity["name"], identity["school_name"], identity["class_no"], identity["student_no"], identity["birth_masked"], None, now, now),
    )
    conn.execute(
        "UPDATE students SET class_no=?, student_no=?, updated_at=? WHERE name=? AND IFNULL(school_name,'')=IFNULL(?, '') AND IFNULL(birth_masked,'')=IFNULL(?, '')",
        (identity["class_no"], identity["student_no"], now, identity["name"], identity["school_name"], identity["birth_masked"]),
    )
    row = conn.execute(
        "SELECT id FROM students WHERE name=? AND IFNULL(school_name,'')=IFNULL(?, '') AND IFNULL(birth_masked,'')=IFNULL(?, '')",
        (identity["name"], identity["school_name"], identity["birth_masked"]),
    ).fetchone()
    return int(row["id"])


def _upsert_document(conn, student_id, identity, page_count, raw_text, metadata, pdf_path, stored_pdf, pdf_hash, method, confidence, now, document_type) -> int:
    # P2-5: re-ingesting the same PDF (same sha256) must refresh the document
    # header too, not just the rows. INSERT OR IGNORE left raw_text / metadata /
    # method / confidence stale. UPSERT on the unique file_sha256 keeps created_at
    # but updates the extraction fields.
    conn.execute(
        "INSERT INTO student_documents(student_id, document_type, source_pdf_path, stored_pdf_path, file_sha256, page_count, issued_at, issuer_school, document_number, verification_number, raw_text, metadata_json, extraction_method, extraction_confidence, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(file_sha256) DO UPDATE SET "
        "student_id=excluded.student_id, source_pdf_path=excluded.source_pdf_path, stored_pdf_path=excluded.stored_pdf_path, "
        "page_count=excluded.page_count, issuer_school=excluded.issuer_school, raw_text=excluded.raw_text, "
        "metadata_json=excluded.metadata_json, extraction_method=excluded.extraction_method, extraction_confidence=excluded.extraction_confidence",
        (student_id, document_type, str(pdf_path), str(stored_pdf), pdf_hash, page_count, None, identity["school_name"], None, None, raw_text, json.dumps(metadata, ensure_ascii=False), method, confidence, now),
    )
    row = conn.execute("SELECT id FROM student_documents WHERE file_sha256=?", (pdf_hash,)).fetchone()
    return int(row["id"])


def _replace_grades(conn, document_id, rows, now) -> None:
    conn.execute("DELETE FROM subject_grades WHERE student_document_id=?", (document_id,))
    for row in rows:
        subject = str(row.get("subject") or "").strip()
        if not subject:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO subject_grades(student_document_id, grade, semester, category, subject, credits, raw_score, achievement, students_count, rank_grade, raw_row, confidence, review_status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (document_id, _int(row.get("grade")), _int(row.get("semester")), row.get("category"), subject, _float(row.get("credits")), row.get("raw_score"), row.get("achievement"), _int(row.get("students_count")), row.get("rank_grade"), json.dumps(row, ensure_ascii=False), _row_conf(row), _row_status(row), now),
        )


def _replace_notes(conn, document_id, rows, now) -> None:
    conn.execute("DELETE FROM subject_special_notes WHERE student_document_id=?", (document_id,))
    for row in rows:
        subject = str(row.get("subject") or "").strip()
        note = str(row.get("note_text") or "").strip()
        if not subject or not note:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO subject_special_notes(student_document_id, grade, semester, subject, note_text, source_page_start, source_page_end, confidence, review_status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (document_id, _int(row.get("grade")), _int(row.get("semester")), subject, note, None, None, _row_conf(row), _row_status(row), now),
        )


def _replace_awards(conn, document_id, rows, now) -> None:
    conn.execute("DELETE FROM awards WHERE student_document_id=?", (document_id,))
    for row in rows:
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO awards(student_document_id, grade, title, awarded_at, issuer, confidence, review_status, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (document_id, _int(row.get("grade")), title, row.get("awarded_at"), row.get("issuer"), _row_conf(row), _row_status(row), now),
        )


# ---------------------------------------------------------------- queries

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
        rows.extend(_search_table(conn, "subject_special_notes", "note_text", terms, limit))
        rows.extend(_search_table(conn, "subject_grades", "raw_row", terms, limit))
        return rows[:limit]
    finally:
        conn.close()


def summary_counts(path: Path, document_id: int) -> dict[str, Any]:
    conn = connect(path)
    try:
        return {
            "subject_grade_rows": _count(conn, "subject_grades", document_id),
            "special_note_rows": _count(conn, "subject_special_notes", document_id),
            "attendance_rows": _count(conn, "attendance_records", document_id),
            "award_rows": _count(conn, "awards", document_id),
            "photos": _photo_count(conn, document_id),
            "confirmed_rows": _confirmed_count(conn, document_id),
            "needs_review_rows": _pending_count(conn, document_id),
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
    # Confinement (P2-7): only ever rmtree a real life_record bundle — one that
    # lives under MIHO_HOME inside a 'life_records' directory. Never delete an
    # arbitrary/relative path or a system root, even if the caller passed one.
    resolved = bundle_dir.resolve()
    home = get_miho_home().resolve()
    if home != resolved and home not in resolved.parents:
        raise ValueError(f"refusing to delete outside MIHO_HOME: {resolved}")
    if "life_records" not in resolved.parts:
        raise ValueError(f"refusing to delete a non-life_record path: {resolved}")
    shutil.rmtree(resolved)
    return True


# ---------------------------------------------------------------- confirm + promote

def confirm_rows(path: Path, document_id: int) -> int:
    """Mark this document's remaining needs_review rows as confirmed (human ok)."""
    conn = connect(path)
    try:
        changed = 0
        for table in ("subject_grades", "subject_special_notes", "attendance_records", "awards"):
            cur = conn.execute(f"UPDATE {table} SET review_status='confirmed' WHERE student_document_id=? AND review_status!='confirmed'", (document_id,))
            changed += cur.rowcount
        conn.commit()
        return changed
    finally:
        conn.close()


def promote_to_central(bundle_path: Path, document_id: int, *, source_thread: str = "", central_path: Path | None = None) -> dict[str, Any]:
    """Copy this document's *confirmed* rows into the central student DB, accumulating
    per student across semesters. Returns counts promoted."""
    bundle = connect(bundle_path)
    try:
        doc = bundle.execute(
            "SELECT d.*, s.name, s.school_name, s.birth_masked, s.profile_photo_path FROM student_documents d JOIN students s ON s.id=d.student_id WHERE d.id=?",
            (document_id,),
        ).fetchone()
        if not doc:
            return {"ok": False, "reason": "document_not_found"}
        # Identity guard (P1-4): never promote a record whose identity key
        # (name + school + birth) is incomplete — it would land as "미상" and
        # collide with 동명이인 in the central DB. Keep it in the thread bundle
        # for a human to complete instead.
        if (not doc["name"]) or doc["name"] == "미상" or (not doc["school_name"]) or (not doc["birth_masked"]):
            return {"ok": False, "reason": "incomplete_identity",
                    "message": "신원(이름·학교·생년월일)이 확정되지 않아 중앙 학생DB로 승격할 수 없어. 원본과 대조해 확정해줘."}
        grades = [dict(r) for r in bundle.execute("SELECT * FROM subject_grades WHERE student_document_id=? AND review_status='confirmed'", (document_id,)).fetchall()]
        notes = [dict(r) for r in bundle.execute("SELECT * FROM subject_special_notes WHERE student_document_id=? AND review_status='confirmed'", (document_id,)).fetchall()]
        attendance = [dict(r) for r in bundle.execute("SELECT * FROM attendance_records WHERE student_document_id=? AND review_status='confirmed'", (document_id,)).fetchall()]
        awards = [dict(r) for r in bundle.execute("SELECT * FROM awards WHERE student_document_id=? AND review_status='confirmed'", (document_id,)).fetchall()]
    finally:
        bundle.close()

    now = now_iso()
    central = connect_central(central_path)
    try:
        central.execute(
            "INSERT OR IGNORE INTO students(name, school_name, birth_masked, profile_photo_path, source_thread, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
            (doc["name"], doc["school_name"], doc["birth_masked"], doc["profile_photo_path"], source_thread, now, now),
        )
        srow = central.execute(
            "SELECT id FROM students WHERE name=? AND IFNULL(school_name,'')=IFNULL(?, '') AND IFNULL(birth_masked,'')=IFNULL(?, '')",
            (doc["name"], doc["school_name"], doc["birth_masked"]),
        ).fetchone()
        student_id = int(srow["id"])
        central.execute("UPDATE students SET updated_at=?, profile_photo_path=COALESCE(?, profile_photo_path) WHERE id=?", (now, doc["profile_photo_path"], student_id))
        if doc["document_type"] == "life_record_mhtml":
            delete_central_duplicate_students(central, student_id, doc["name"], doc["birth_masked"], source_thread)
            clear_central_student_rows(central, student_id)
        for g in grades:
            central.execute(
                "INSERT OR REPLACE INTO central_grades(student_id, grade, semester, category, subject, credits, raw_score, achievement, students_count, rank_grade, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (student_id, g["grade"], g["semester"], g["category"], g["subject"], g["credits"], g["raw_score"], g["achievement"], g["students_count"], g["rank_grade"], now),
            )
        for n in notes:
            central.execute(
                "INSERT OR REPLACE INTO central_notes(student_id, grade, semester, subject, note_text, updated_at) VALUES(?,?,?,?,?,?)",
                (student_id, n["grade"], n["semester"], n["subject"], n["note_text"], now),
            )
        for a in attendance:
            central.execute(
                "INSERT OR REPLACE INTO central_attendance(student_id, grade, school_days, detail_json, special_note, updated_at) VALUES(?,?,?,?,?,?)",
                (student_id, a["grade"], a["school_days"], None, a["special_note"], now),
            )
        for w in awards:
            central.execute(
                "INSERT OR REPLACE INTO central_awards(student_id, grade, title, awarded_at, issuer, updated_at) VALUES(?,?,?,?,?,?)",
                (student_id, w["grade"], w["title"], w["awarded_at"], w["issuer"], now),
            )
        central.execute(
            "INSERT INTO central_promotions(student_id, source_document_sha256, source_thread, promoted_at) VALUES(?,?,?,?)",
            (student_id, doc["file_sha256"], source_thread, now),
        )
        central.commit()
        return {"ok": True, "central_student_id": student_id, "grades": len(grades), "notes": len(notes), "attendance": len(attendance), "awards": len(awards)}
    finally:
        central.close()


def lookup_central(query: str, *, limit: int = 10, central_path: Path | None = None) -> dict[str, Any]:
    path = central_path or central_db_path()
    if not path.exists():
        return {"students": [], "total": 0}
    terms = [t for t in query.split() if t]
    conn = connect_central(path)
    try:
        students = [dict(r) for r in conn.execute("SELECT * FROM students ORDER BY updated_at DESC LIMIT 200").fetchall()]
        matched = []
        for s in students:
            hay = f"{s.get('name','')} {s.get('school_name','')}"
            if terms and not all(t in hay for t in terms):
                continue
            sid = s["id"]
            s["grades"] = [dict(r) for r in conn.execute("SELECT grade, semester, category, subject, raw_score, achievement, rank_grade FROM central_grades WHERE student_id=? ORDER BY grade, semester", (sid,)).fetchall()]
            s["notes_count"] = int(conn.execute("SELECT COUNT(*) AS n FROM central_notes WHERE student_id=?", (sid,)).fetchone()["n"])
            s["attendance"] = [dict(r) for r in conn.execute("SELECT grade, school_days, special_note FROM central_attendance WHERE student_id=? ORDER BY grade", (sid,)).fetchall()]
            s["awards_count"] = int(conn.execute("SELECT COUNT(*) AS n FROM central_awards WHERE student_id=?", (sid,)).fetchone()["n"])
            matched.append(s)
            if len(matched) >= limit:
                break
        return {"students": matched, "total": len(matched)}
    finally:
        conn.close()


# ---------------------------------------------------------------- small helpers

def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _count(conn: sqlite3.Connection, table: str, document_id: int) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE student_document_id=?", (document_id,)).fetchone()["n"])


def _photo_count(conn: sqlite3.Connection, document_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM student_photos WHERE document_id=?", (document_id,)).fetchone()["n"])


def _confirmed_count(conn: sqlite3.Connection, document_id: int) -> int:
    total = 0
    for table in ("subject_grades", "subject_special_notes", "attendance_records", "awards"):
        total += int(conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE student_document_id=? AND review_status='confirmed'", (document_id,)).fetchone()["n"])
    return total


def _pending_count(conn: sqlite3.Connection, document_id: int) -> int:
    total = 0
    for table in ("subject_grades", "subject_special_notes", "attendance_records", "awards"):
        total += int(conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE student_document_id=? AND review_status!='confirmed'", (document_id,)).fetchone()["n"])
    return total


def _search_table(conn: sqlite3.Connection, table: str, field: str, terms: list[str], limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 200").fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        text = str(row[field] or "")
        if terms and not all(term in text for term in terms):
            continue
        out.append({"table": table, "row_id": row["id"], "snippet": text[:600], "review_status": row["review_status"] if "review_status" in row.keys() else None})
        if len(out) >= limit:
            break
    return out
