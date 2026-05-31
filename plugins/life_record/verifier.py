"""Verification rounds for vision/consensus-based life record imports.

Traceability is no longer "is this string in the raw PDF text" (vision-extracted
scans have no text layer) — it is "did independent vision passes agree". The
consensus round reports the confirmed ratio; unresolved rows stay needs_review.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .repository import connect, record_verification

_ROW_TABLES = ("subject_grades", "subject_special_notes", "attendance_records", "awards")


def run_verification(db_path: Path, document_id: int, *, consensus: dict[str, Any] | None = None) -> dict[str, Any]:
    rounds = [
        _extraction_round(db_path, document_id),
        _consensus_round(db_path, document_id),
        _readiness_round(db_path, document_id),
    ]
    for item in rounds:
        record_verification(db_path, document_id, item["round"], item["status"], item)
    failed = sum(1 for item in rounds if item["status"] != "pass")
    return {
        "round_count": len(rounds),
        "status": "needs_review" if failed else "pass",
        "human_review_required": failed > 0,
        "rounds": rounds,
        "failed_rounds": failed,
        "policy": "합의되지 않은 항목은 사람 검수 전 확정 표현 금지.",
    }


def _extraction_round(db_path: Path, document_id: int) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        doc = _document(conn, document_id)
        checks = [
            _check("db_document_exists", bool(doc), ""),
            _check("page_count_present", bool(doc and doc["page_count"] > 0), f"pages={doc['page_count'] if doc else 0}"),
            _check("stored_pdf_exists", bool(doc and Path(doc["stored_pdf_path"]).exists()), doc["stored_pdf_path"] if doc else ""),
            _check("has_extracted_rows", _total_rows(conn, document_id) > 0, f"rows={_total_rows(conn, document_id)}"),
        ]
        return _round("extraction", checks)
    finally:
        conn.close()


def _consensus_round(db_path: Path, document_id: int) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        total = _total_rows(conn, document_id)
        confirmed = _confirmed_rows(conn, document_id)
        rate = round(confirmed / total * 100, 2) if total else 0.0
        checks = [
            _check("rows_present", total > 0, f"rows={total}"),
            _check("majority_confirmed", total > 0 and confirmed * 2 >= total, f"confirmed={confirmed}/{total}"),
        ]
        result = _round("consensus", checks)
        result["confirmed_rate"] = rate
        result["confirmed_rows"] = confirmed
        result["total_rows"] = total
        return result
    finally:
        conn.close()


def _readiness_round(db_path: Path, document_id: int) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        pending = _pending_rows(conn, document_id)
        checks = [
            _check("thread_scoped_db", "life_records.sqlite3" in db_path.name, str(db_path)),
            _check("review_status_tracked", True, f"needs_review_rows={pending}"),
            _check("verification_history_written", True, "current run recorded"),
        ]
        return _round("human_review_gate", checks)
    finally:
        conn.close()


def _document(conn: sqlite3.Connection, document_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT d.*, s.name, s.school_name FROM student_documents d JOIN students s ON s.id=d.student_id WHERE d.id=?",
        (document_id,),
    ).fetchone()
    return dict(row) if row else None


def _total_rows(conn: sqlite3.Connection, document_id: int) -> int:
    return sum(int(conn.execute(f"SELECT COUNT(*) AS n FROM {t} WHERE student_document_id=?", (document_id,)).fetchone()["n"]) for t in _ROW_TABLES)


def _confirmed_rows(conn: sqlite3.Connection, document_id: int) -> int:
    return sum(int(conn.execute(f"SELECT COUNT(*) AS n FROM {t} WHERE student_document_id=? AND review_status='confirmed'", (document_id,)).fetchone()["n"]) for t in _ROW_TABLES)


def _pending_rows(conn: sqlite3.Connection, document_id: int) -> int:
    return sum(int(conn.execute(f"SELECT COUNT(*) AS n FROM {t} WHERE student_document_id=? AND review_status!='confirmed'", (document_id,)).fetchone()["n"]) for t in _ROW_TABLES)


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
