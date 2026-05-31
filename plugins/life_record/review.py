"""Review HTML generation for vision-based life record imports."""

from __future__ import annotations

import html
from pathlib import Path

from .repository import connect


def write_review_html(db_path: Path, document_id: int, out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        doc = conn.execute(
            "SELECT d.*, s.name, s.school_name, s.profile_photo_path FROM student_documents d JOIN students s ON s.id=d.student_id WHERE d.id=?",
            (document_id,),
        ).fetchone()
        grades = conn.execute(
            "SELECT grade, semester, subject, raw_score, rank_grade, achievement, review_status FROM subject_grades WHERE student_document_id=? ORDER BY grade, semester, subject",
            (document_id,),
        ).fetchall()
        notes = conn.execute(
            "SELECT grade, subject, note_text, review_status FROM subject_special_notes WHERE student_document_id=? ORDER BY grade, subject",
            (document_id,),
        ).fetchall()
        attendance = conn.execute(
            "SELECT grade, school_days, special_note, review_status FROM attendance_records WHERE student_document_id=? ORDER BY grade",
            (document_id,),
        ).fetchall()
        awards = conn.execute(
            "SELECT grade, title, awarded_at, review_status FROM awards WHERE student_document_id=? ORDER BY grade",
            (document_id,),
        ).fetchall()
    finally:
        conn.close()

    name = doc["name"] if doc else "미상"
    school = doc["school_name"] if doc else ""
    photo = doc["profile_photo_path"] if doc else None

    parts: list[str] = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>",
        "<style>",
        "body{font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif;background:#f6f7f9;color:#1d2430;margin:0;padding:24px;}",
        ".card{max-width:920px;margin:0 auto;background:#fff;border-radius:14px;box-shadow:0 2px 14px rgba(0,0,0,.06);padding:24px;}",
        "h1{font-size:20px;margin:0 0 4px;} .sub{color:#6b7280;font-size:13px;margin-bottom:18px;}",
        "table{width:100%;border-collapse:collapse;margin:10px 0 22px;font-size:13px;}",
        "th,td{border:1px solid #e5e7eb;padding:6px 8px;text-align:left;vertical-align:top;}",
        "th{background:#f3f4f6;} h2{font-size:15px;margin:18px 0 6px;}",
        ".confirmed{color:#0a7d32;font-weight:600;} .needs_review{color:#b4690e;font-weight:600;}",
        ".photo{float:right;width:96px;height:auto;border-radius:8px;margin-left:16px;}",
        ".warn{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:10px 12px;font-size:13px;color:#9a3412;margin-bottom:16px;}",
        "</style></head><body><div class='card'>",
    ]
    if photo and Path(photo).exists():
        parts.append(f"<img class='photo' src='file://{html.escape(photo)}' alt='photo'>")
    parts.append(f"<h1>{html.escape(name)} 생기부 검수</h1>")
    parts.append(f"<div class='sub'>{html.escape(school)} · 문서 #{document_id} · {doc['page_count'] if doc else 0}p · {html.escape(doc['extraction_method'] if doc else '')}</div>")
    parts.append("<div class='warn'>합의(confirmed)되지 않은 needs_review 항목은 사람 검수 후 확정하세요. 검수 완료 시 life_record_confirm로 중앙DB에 반영됩니다.</div>")

    parts.append("<h2>교과 성적</h2>")
    parts.append(_table(["학년", "학기", "과목", "원점수", "석차/성취", "상태"], [[r["grade"], r["semester"], r["subject"], r["raw_score"], r["rank_grade"] or r["achievement"], _status(r["review_status"])] for r in grades]))

    parts.append("<h2>세부능력 및 특기사항</h2>")
    parts.append(_table(["학년", "과목", "내용", "상태"], [[r["grade"], r["subject"], (r["note_text"] or "")[:400], _status(r["review_status"])] for r in notes]))

    parts.append("<h2>출결</h2>")
    parts.append(_table(["학년", "수업일수", "비고", "상태"], [[r["grade"], r["school_days"], r["special_note"], _status(r["review_status"])] for r in attendance]))

    parts.append("<h2>수상</h2>")
    parts.append(_table(["학년", "수상명", "일자", "상태"], [[r["grade"], r["title"], r["awarded_at"], _status(r["review_status"])] for r in awards]))

    parts.append("</div></body></html>")
    out = out_dir / "생기부_검수.html"
    out.write_text("".join(parts), encoding="utf-8")
    return str(out)


def _status(value: str | None) -> str:
    cls = "confirmed" if value == "confirmed" else "needs_review"
    return f"<span class='{cls}'>{html.escape(str(value or 'needs_review'))}</span>"


def _table(headers: list[str], rows: list[list]) -> str:
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = []
    for row in rows:
        cells = "".join(f"<td>{c if (isinstance(c, str) and c.startswith('<span')) else html.escape('' if c is None else str(c))}</td>" for c in row)
        body.append(f"<tr>{cells}</tr>")
    if not body:
        body.append(f"<tr><td colspan='{len(headers)}' style='color:#9ca3af'>없음</td></tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"
