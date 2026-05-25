"""Review HTML generation for life record imports."""

from __future__ import annotations

import html
import sqlite3
from pathlib import Path
from typing import Any


def write_review_html(db_path: Path, document_id: int, out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        doc = conn.execute(
            "SELECT d.*, s.name, s.school_name, s.profile_photo_path FROM student_documents d JOIN students s ON s.id=d.student_id WHERE d.id=?",
            (document_id,),
        ).fetchone()
        if not doc:
            raise ValueError(f"document not found: {document_id}")
        rows = _section_rows(conn, document_id)
        path = out_dir / f"{_safe(doc['name'])}_생기부_검수.html"
        path.write_text(_html(dict(doc), rows), encoding="utf-8")
        return str(path)
    finally:
        conn.close()


def _section_rows(conn: sqlite3.Connection, document_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT section_type, page_start, page_end, confidence, review_status, raw_text FROM life_record_sections WHERE student_document_id=? ORDER BY page_start",
        (document_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _html(doc: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    photo = ""
    if doc.get("profile_photo_path") and Path(doc["profile_photo_path"]).exists():
        photo = f"<img class='photo' src='{html.escape(doc['profile_photo_path'])}'>"
    body = "\n".join(_row(row) for row in rows)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>생기부 검수 - {html.escape(str(doc['name']))}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;margin:24px;background:#f8fafc;color:#111827}}
.card{{background:white;border:1px solid #d7dce5;border-radius:12px;padding:16px;margin-bottom:16px;box-shadow:0 2px 10px #0000000f}}
.head{{display:flex;gap:18px;align-items:flex-start}}.photo{{width:132px;border:1px solid #ccd3df;border-radius:10px}}
table{{border-collapse:collapse;width:100%;font-size:13px;background:white}}th,td{{border:1px solid #d7dce5;padding:8px;vertical-align:top}}th{{background:#111827;color:white}}
pre{{white-space:pre-wrap;max-height:260px;overflow:auto;margin:0;line-height:1.45}}.warn{{color:#b45309;font-weight:700}}
</style></head><body>
<section class="card head">{photo}<div><h1>생기부 DB 검수</h1>
<p><b>학생</b> {html.escape(str(doc['name']))} / {html.escape(str(doc.get('school_name') or ''))}</p>
<p><b>문서 ID</b> {doc['id']} / <b>페이지</b> {doc['page_count']} / <b>원문</b> {len(doc.get('raw_text') or ''):,}자</p>
<p><b>PDF</b> <code>{html.escape(str(doc['stored_pdf_path']))}</code></p>
<p class="warn">needs_review 값은 PDF 원문 대조 후 확정해야 합니다.</p></div></section>
<section class="card"><table><thead><tr><th>섹션</th><th>페이지</th><th>신뢰도</th><th>상태</th><th>원문 미리보기</th></tr></thead><tbody>{body}</tbody></table></section>
</body></html>"""


def _row(row: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(str(row['section_type']))}</td>"
        f"<td>{row['page_start']}-{row['page_end']}</td>"
        f"<td>{float(row['confidence']):.2f}</td>"
        f"<td>{html.escape(str(row['review_status']))}</td>"
        f"<td><pre>{html.escape(str(row['raw_text'])[:1600])}</pre></td>"
        "</tr>"
    )


def _safe(value: Any) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "student"))[:80]
