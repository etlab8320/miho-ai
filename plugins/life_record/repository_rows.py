"""Row persistence helpers for life-record repository."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .consensus import CONFIRMED


def replace_sections(conn: sqlite3.Connection, document_id: int, rows: list[dict[str, Any]], now: str) -> None:
    conn.execute("DELETE FROM life_record_sections WHERE student_document_id=?", (document_id,))
    for index, row in enumerate(rows, start=1):
        section_type = str(row.get("section_type") or "").strip()
        raw_text = str(row.get("raw_text") or "").strip()
        if not section_type or not raw_text:
            continue
        conn.execute(
            "INSERT INTO life_record_sections(student_document_id, section_type, page_start, page_end, raw_text, parsed_json, confidence, review_status, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                document_id,
                section_type,
                _int(row.get("page_start")) or index,
                _int(row.get("page_end")) or index,
                raw_text,
                json.dumps(row.get("parsed_json") or {"method": "neis_mhtml_table_v1"}, ensure_ascii=False),
                _row_conf(row, 0.93),
                _row_status(row),
                now,
            ),
        )


def replace_attendance(conn: sqlite3.Connection, document_id: int, rows: list[dict[str, Any]], now: str) -> None:
    conn.execute("DELETE FROM attendance_records WHERE student_document_id=?", (document_id,))
    for row in rows:
        grade = _int(row.get("grade"))
        if grade is None:
            continue
        detail = _attendance_detail(row)
        conn.execute(
            "INSERT OR REPLACE INTO attendance_records(student_document_id, grade, school_days, absent_disease, absent_unexcused, absent_other, late_disease, late_unexcused, late_other, early_leave_disease, early_leave_unexcused, early_leave_other, result_disease, result_unexcused, result_other, special_note, confidence, review_status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                document_id,
                grade,
                _int(row.get("school_days")),
                detail["absent_disease"],
                detail["absent_unexcused"],
                detail["absent_other"],
                detail["late_disease"],
                detail["late_unexcused"],
                detail["late_other"],
                detail["early_leave_disease"],
                detail["early_leave_unexcused"],
                detail["early_leave_other"],
                detail["result_disease"],
                detail["result_unexcused"],
                detail["result_other"],
                str(row.get("special_note") or ""),
                _row_conf(row, 0.93),
                _row_status(row),
                now,
            ),
        )


def delete_superseded_mhtml_documents(conn: sqlite3.Connection, student_id: int, keep_document_id: int) -> int:
    rows = conn.execute(
        "SELECT id FROM student_documents WHERE student_id=? AND id<>? AND (document_type='life_record_mhtml' OR extraction_method LIKE '%mhtml%')",
        (student_id, keep_document_id),
    ).fetchall()
    removed = 0
    for row in rows:
        document_id = int(row["id"])
        for table, column in (
            ("attendance_records", "student_document_id"),
            ("subject_grades", "student_document_id"),
            ("subject_special_notes", "student_document_id"),
            ("life_record_sections", "student_document_id"),
            ("student_photos", "document_id"),
            ("extraction_audit_logs", "document_id"),
            ("verification_runs", "document_id"),
        ):
            conn.execute(f"DELETE FROM {table} WHERE {column}=?", (document_id,))
        conn.execute("DELETE FROM student_documents WHERE id=?", (document_id,))
        removed += 1
    return removed


def clear_central_student_rows(conn: sqlite3.Connection, student_id: int) -> None:
    for table in ("central_grades", "central_notes", "central_attendance", "central_awards"):
        conn.execute(f"DELETE FROM {table} WHERE student_id=?", (student_id,))


def delete_central_duplicate_students(conn: sqlite3.Connection, keep_student_id: int, name: str, birth_masked: str, source_thread: str) -> int:
    rows = conn.execute(
        "SELECT id FROM students WHERE id<>? AND name=? AND birth_masked=? AND IFNULL(source_thread,'')=IFNULL(?, '')",
        (keep_student_id, name, birth_masked, source_thread),
    ).fetchall()
    removed = 0
    for row in rows:
        student_id = int(row["id"])
        clear_central_student_rows(conn, student_id)
        conn.execute("DELETE FROM central_promotions WHERE student_id=?", (student_id,))
        conn.execute("DELETE FROM students WHERE id=?", (student_id,))
        removed += 1
    return removed


def _attendance_detail(row: dict[str, Any]) -> dict[str, int]:
    detail = {
        "absent_disease": _int(row.get("absent_disease")) or 0,
        "absent_unexcused": _int(row.get("absent_unexcused")) or 0,
        "absent_other": _int(row.get("absent_other")) or 0,
        "late_disease": _int(row.get("late_disease")) or 0,
        "late_unexcused": _int(row.get("late_unexcused")) or 0,
        "late_other": _int(row.get("late_other")) or 0,
        "early_leave_disease": _int(row.get("early_leave_disease")) or 0,
        "early_leave_unexcused": _int(row.get("early_leave_unexcused")) or 0,
        "early_leave_other": _int(row.get("early_leave_other")) or 0,
        "result_disease": _int(row.get("result_disease")) or 0,
        "result_unexcused": _int(row.get("result_unexcused")) or 0,
        "result_other": _int(row.get("result_other")) or 0,
    }
    _merge_triplet(detail, "absent", row.get("absence"))
    _merge_triplet(detail, "late", row.get("late"))
    _merge_triplet(detail, "early_leave", row.get("early_leave"))
    return detail


def _merge_triplet(detail: dict[str, int], prefix: str, value: Any) -> None:
    if not value:
        return
    parts = [p.strip() for p in str(value).split("/")]
    for key, part in zip(("disease", "unexcused", "other"), parts):
        if part and part != ".":
            detail[f"{prefix}_{key}"] = _int(part) or 0


def _row_status(row: dict[str, Any]) -> str:
    return CONFIRMED if row.get("_status") == CONFIRMED else "needs_review"


def _row_conf(row: dict[str, Any], default: float) -> float:
    try:
        return float(row.get("_confidence") or default)
    except (TypeError, ValueError):
        return default


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
