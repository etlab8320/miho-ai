"""HTML template for daily academy attendance roster images."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from .brand_assets import academy_brand_logo_src
from .report_fonts import PRETENDARD_FAMILY, report_font_css


STATUS_LABELS = {"present": "출석", "late": "지각", "absent": "결석", "unknown": "미체크"}
SLOT_LABELS = {"morning": "오전반", "afternoon": "오후반", "evening": "저녁반"}

# Same Korean-first stack as report_design: bundled Pretendard (base64 @font-face)
# first so the sheet renders cleanly offline, then robust system fallbacks.
_FONT_STACK = (
    f"'{PRETENDARD_FAMILY}','Goyang','GoyangDeogyang','Pretendard',"
    "'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif"
)
# Per-status accent so each row's state reads at a glance (no domain literals).
STATUS_CLASSES = {"present": "present", "late": "late", "absent": "absent", "unknown": "unknown"}


def render_attendance_day_html(payload: dict[str, Any], *, logo_path: Path | None = None) -> str:
    rows = _rows_html(payload)
    date_text = escape(str(payload.get("date") or ""))
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    total = sum(int(summary.get(key) or 0) for key in STATUS_LABELS)
    brand = _brand_html(logo_path)
    empty = "<div class='empty'>출석 대상 명단이 없어.</div>" if not rows else ""
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
{report_font_css()}
:root {{
  --bg:#eef0f4;--card:#ffffff;--ink:#16181d;--ink-soft:#3a4150;--muted:#717784;
  --line:#e6e9ef;--line-soft:#f0f2f6;--row-alt:#f8fafc;--neutral-soft:#eef0f4;--accent:#111827;
  --present:#0a8f6a;--present-soft:#e4f6ef;--late:#9a6a00;--late-soft:#fdf3da;
  --absent:#c0392b;--absent-soft:#fdecea;--unknown:#5b6472;--unknown-soft:#eef0f4;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ background: var(--bg); }}
body {{ width: 1200px; color: var(--ink); font-family: {_FONT_STACK};
  -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; padding: 44px 40px; }}
.sheet {{ width: 1120px; margin: 0 auto; background: var(--card); border-radius: 24px; overflow: hidden;
  border: 1px solid #eceef3; box-shadow: 0 1px 2px rgba(20,24,29,.05), 0 28px 64px -28px rgba(20,24,29,.28); }}
.top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 24px;
  padding: 38px 42px 24px; border-bottom: 1px solid var(--line); background: linear-gradient(180deg,#fbfcfe,#ffffff); }}
.headline {{ min-width: 0; }}
.title {{ font-size: 38px; font-weight: 700; letter-spacing: -.025em; line-height: 1.1; }}
.title::after {{ content: ""; display: block; width: 46px; height: 4px; border-radius: 999px; background: var(--accent); margin-top: 13px; }}
.subtitle {{ margin-top: 13px; font-size: 15px; color: var(--muted); font-weight: 500; letter-spacing: -.01em; }}
.eyebrow {{ font-size: 13px; font-weight: 700; color: var(--muted); letter-spacing: .02em; margin-bottom: 8px; }}
.brandtag {{ display: flex; flex-direction: column; align-items: flex-end; gap: 9px; flex: none; }}
.brandtag .stamp {{ height: 52px; width: auto; opacity: .96; }}
.brandtag .logo-text {{ font-size: 30px; font-weight: 800; color: #c0392b; border: 3px solid #c0392b; border-radius: 11px; padding: 6px 14px; }}
.brandtag .txt {{ text-align: right; font-size: 11.5px; color: #aab0bd; font-weight: 600; line-height: 1.5; }}
.brandtag .txt b {{ color: var(--ink); font-weight: 700; display: block; font-size: 14px; letter-spacing: -.01em; }}
.body {{ padding: 22px 42px 30px; }}
.summary {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 24px; }}
.metric {{ border: 1px solid var(--line); border-radius: 14px; padding: 16px 18px; background: #fcfdff; }}
.metric.present {{ background: var(--present-soft); border-color: transparent; }}
.metric.late {{ background: var(--late-soft); border-color: transparent; }}
.metric.absent {{ background: var(--absent-soft); border-color: transparent; }}
.metric.unknown {{ background: var(--unknown-soft); border-color: transparent; }}
.label {{ font-size: 13.5px; font-weight: 600; color: var(--muted); }}
.value {{ margin-top: 6px; font-size: 32px; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; line-height: 1; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
th, td {{ padding: 14px 16px; font-size: 16px; text-align: left; vertical-align: middle; }}
thead th {{ font-size: 12.5px; font-weight: 700; color: var(--muted); letter-spacing: .01em;
  border-bottom: 1.5px solid var(--line); padding: 8px 16px 11px; white-space: nowrap; }}
tbody td {{ border-bottom: 1px solid var(--line-soft); }}
tbody tr:nth-child(even) td {{ background: var(--row-alt); }}
tbody tr:last-child td {{ border-bottom: none; }}
.num {{ width: 64px; text-align: center; color: var(--muted); font-size: 14px; font-variant-numeric: tabular-nums; }}
.slot {{ width: 116px; }}
.slot .pill {{ display: inline-flex; align-items: center; height: 26px; padding: 0 11px; border-radius: 8px;
  background: var(--neutral-soft); color: var(--ink-soft); font-size: 13px; font-weight: 700; }}
.name {{ width: 220px; font-size: 18px; font-weight: 700; color: var(--ink); letter-spacing: -.01em; }}
.profile {{ color: var(--muted); font-size: 14px; font-weight: 500; }}
.status {{ width: 116px; text-align: center; }}
.status .tag {{ display: inline-flex; align-items: center; justify-content: center; min-width: 56px; height: 28px;
  padding: 0 12px; border-radius: 999px; font-size: 13.5px; font-weight: 700; }}
.status .present {{ background: var(--present-soft); color: var(--present); }}
.status .late {{ background: var(--late-soft); color: var(--late); }}
.status .absent {{ background: var(--absent-soft); color: var(--absent); }}
.status .unknown {{ background: var(--unknown-soft); color: var(--unknown); }}
.empty {{ min-height: 420px; display: grid; place-items: center; border: 1px dashed var(--line);
  border-radius: 16px; font-size: 22px; font-weight: 600; color: var(--muted); }}
</style>
</head>
<body>
  <main class="sheet">
    <section class="top">
      <div class="headline">
        <div class="eyebrow">출석 대상 명단</div>
        <div class="title">{date_text}</div>
        <div class="subtitle">전체 {total}명 · 수업 없는 날은 포함하지 않음</div>
      </div>
      {brand}
    </section>
    <div class="body">
      {_summary_html(summary, total)}
      {rows}
      {empty}
    </div>
  </main>
</body>
</html>"""


def attendance_day_image_height(payload: dict[str, Any]) -> int:
    count = sum(len(rows) for rows in (payload.get("slots") or {}).values() if isinstance(rows, list))
    return 420 + max(1, count) * 57


def _summary_html(summary: dict[str, Any], total: int) -> str:
    metrics = [("전체", total, ""), *[(label, int(summary.get(key) or 0), key) for key, label in STATUS_LABELS.items()]]
    return "<section class='summary'>" + "".join(_metric_html(label, value, key) for label, value, key in metrics) + "</section>"


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
    css = escape(STATUS_CLASSES.get(status, "unknown"))
    return (
        "<tr>"
        f"<td class='num'>{index}</td><td class='slot'><span class='pill'>{escape(SLOT_LABELS.get(slot, slot))}</span></td>"
        f"<td class='name'>{name}</td><td class='profile'>{profile or '프로필 확인 필요'}</td>"
        f"<td class='status'><span class='tag {css}'>{escape(STATUS_LABELS.get(status, '미체크'))}</span></td>"
        "</tr>"
    )


def _metric_html(label: str, value: int, key: str) -> str:
    cls = f" {escape(key)}" if key else ""
    return f"<div class='metric{cls}'><div class='label'>{escape(label)}</div><div class='value'>{value}</div></div>"


def _brand_html(path: Path | None) -> str:
    logo_src = academy_brand_logo_src(path)
    stamp = (
        f"<img class='stamp' src='{escape(logo_src, quote=True)}' alt='stamp'>"
        if logo_src
        else "<div class='logo-text'>MAX</div>"
    )
    return f"<div class='brandtag'>{stamp}<div class='txt'><b>Miho AI</b>PACA / Peak</div></div>"
