"""HTML template for daily academy attendance roster images."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from .brand_assets import academy_brand_logo_src


STATUS_LABELS = {"present": "출석", "late": "지각", "absent": "결석", "unknown": "미체크"}
SLOT_LABELS = {"morning": "오전반", "afternoon": "오후반", "evening": "저녁반"}


def render_attendance_day_html(payload: dict[str, Any], *, logo_path: Path | None = None) -> str:
    rows = _rows_html(payload)
    date_text = escape(str(payload.get("date") or ""))
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    total = sum(int(summary.get(key) or 0) for key in STATUS_LABELS)
    logo = _logo_html(logo_path)
    empty = "<div class='empty'>출석 대상 명단이 없어.</div>" if not rows else ""
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: #f4f6f8; color: #20242a; }}
body {{ width: 1200px; min-height: 100vh; font-family: "Apple SD Gothic Neo", "Noto Sans KR", "Pretendard", sans-serif; }}
.sheet {{ width: 1120px; margin: 36px auto; padding: 32px; background: #ffffff; border: 1px solid #d9e0e7; border-radius: 18px; }}
.top {{ display: flex; justify-content: space-between; align-items: center; gap: 24px; margin-bottom: 24px; }}
.eyebrow {{ font-size: 18px; font-weight: 900; color: #b71d25; }}
h1 {{ margin: 8px 0; font-size: 46px; line-height: 1.05; letter-spacing: 0; }}
.meta {{ font-size: 21px; color: #5f6873; font-weight: 800; }}
.logo {{ width: 210px; max-height: 92px; object-fit: contain; object-position: right center; }}
.logo-text {{ font-size: 40px; font-weight: 1000; color: #d11d28; border: 5px solid #d11d28; border-radius: 12px; padding: 8px 18px; }}
.summary {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 22px; }}
.metric {{ border: 1px solid #dce3ea; border-radius: 12px; padding: 14px; background: #f8fafc; }}
.label {{ font-size: 16px; font-weight: 900; color: #66717d; }}
.value {{ margin-top: 4px; font-size: 30px; font-weight: 1000; color: #242930; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; overflow: hidden; border-radius: 12px; }}
th {{ padding: 12px 10px; background: #26313d; color: #fff; font-size: 17px; text-align: left; }}
td {{ padding: 12px 10px; border-bottom: 1px solid #e6ebf0; font-size: 18px; font-weight: 800; vertical-align: middle; }}
tbody tr:nth-child(even) {{ background: #f8fafc; }}
.num {{ width: 70px; text-align: center; color: #626d78; }}
.name {{ width: 240px; font-size: 21px; font-weight: 1000; color: #1f252c; }}
.slot {{ width: 130px; }}
.status {{ width: 120px; }}
.empty {{ min-height: 420px; display: grid; place-items: center; border: 1px solid #dce3ea; border-radius: 14px; font-size: 28px; font-weight: 900; color: #5f6873; }}
</style>
</head>
<body>
  <main class="sheet">
    <section class="top">
      <div>
        <div class="eyebrow">출석 대상 명단</div>
        <h1>{date_text}</h1>
        <div class="meta">전체 {total}명 · 수업 없는 날은 포함하지 않음</div>
      </div>
      {logo}
    </section>
    {_summary_html(summary, total)}
    {rows}
    {empty}
  </main>
</body>
</html>"""


def attendance_day_image_height(payload: dict[str, Any]) -> int:
    count = sum(len(rows) for rows in (payload.get("slots") or {}).values() if isinstance(rows, list))
    return 330 + max(1, count) * 48


def _summary_html(summary: dict[str, Any], total: int) -> str:
    metrics = [("전체", total), *[(label, int(summary.get(key) or 0)) for key, label in STATUS_LABELS.items()]]
    return "<section class='summary'>" + "".join(_metric_html(label, value) for label, value in metrics) + "</section>"


def _rows_html(payload: dict[str, Any]) -> str:
    rows: list[str] = []
    index = 1
    slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
    for slot, slot_rows in slots.items():
        if not isinstance(slot_rows, list):
            continue
        for row in slot_rows:
            if isinstance(row, dict):
                rows.append(_row_html(index, str(slot), row))
                index += 1
    if not rows:
        return ""
    return "<table><thead><tr><th class='num'>#</th><th class='slot'>반</th><th class='name'>이름</th><th>학교/학년</th><th class='status'>상태</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _row_html(index: int, slot: str, row: dict[str, Any]) -> str:
    name = escape(str(row.get("name") or row.get("student_name") or row.get("student_id") or "이름 없음"))
    profile = escape(" · ".join(part for part in (str(row.get("school") or ""), str(row.get("grade") or "")) if part))
    status = str(row.get("attendance_status") or "unknown")
    return (
        "<tr>"
        f"<td class='num'>{index}</td><td class='slot'>{escape(SLOT_LABELS.get(slot, slot))}</td>"
        f"<td class='name'>{name}</td><td>{profile or '프로필 확인 필요'}</td>"
        f"<td class='status'>{escape(STATUS_LABELS.get(status, '미체크'))}</td>"
        "</tr>"
    )


def _metric_html(label: str, value: int) -> str:
    return f"<div class='metric'><div class='label'>{escape(label)}</div><div class='value'>{value}</div></div>"


def _logo_html(path: Path | None) -> str:
    logo_src = academy_brand_logo_src(path)
    if logo_src:
        return f"<img class='logo' src='{escape(logo_src, quote=True)}' alt='MAX 체대입시'>"
    return "<div class='logo-text'>MAX</div>"
