"""HTML template for student attendance calendar images."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape
from pathlib import Path
from typing import Any

from .brand_assets import academy_brand_logo_src
from .report_fonts import PRETENDARD_FAMILY, report_font_css

# Same Korean-first stack as report_design (bundled Pretendard first, then fallbacks).
_FONT_STACK = (
    f"'{PRETENDARD_FAMILY}','Goyang','GoyangDeogyang','Pretendard',"
    "'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif"
)


STATUS_LABELS = {
    "present": "출석",
    "late": "지각",
    "absent": "결석",
    "unchecked": "미체크",
    "upcoming": "예정",
    "excused": "인정",
    "makeup": "보충",
}
STATUS_CLASSES = {
    "present": "present",
    "late": "late",
    "absent": "absent",
    "unchecked": "unchecked",
    "upcoming": "upcoming",
    "excused": "excused",
    "makeup": "makeup",
}
SLOT_LABELS = {"morning": "오전", "afternoon": "오후", "evening": "저녁"}
WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def render_attendance_calendar_html(
    payload: dict[str, Any],
    *,
    logo_path: Path | None = None,
    today: date | None = None,
) -> str:
    student = payload.get("student") if isinstance(payload.get("student"), dict) else {}
    reference_day = today or _parse_day(str(payload.get("today") or "")) or date.today()
    start_day = _parse_day(str(payload.get("start_date") or ""))
    end_day = _parse_day(str(payload.get("end_date") or ""))
    rows = _attendance_rows(payload, reference_day)
    summary = _display_summary(payload, rows)
    calendar_days = _calendar_days(start_day, end_day)
    cells = "\n".join(_calendar_cell(day, rows.get(day.isoformat()), start_day, end_day) for day in calendar_days)
    stats = "\n".join(_stat(label, summary.get(key, 0), key) for key, label in _summary_order())
    absences = _absence_note_html(rows)
    brand = _brand_html(logo_path)
    name = escape(str(student.get("name") or "학생"))
    school = escape(_profile_text(student))
    period = escape(_period_label(start_day, end_day))
    month = escape(_month_label(start_day, end_day))
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
{report_font_css()}
:root {{
  --bg:#eef0f4;--card:#ffffff;--ink:#16181d;--ink-soft:#3a4150;--muted:#717784;
  --line:#e6e9ef;--line-soft:#f0f2f6;--row-alt:#f8fafc;--neutral-soft:#eef0f4;--accent:#111827;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ background: var(--bg); }}
body {{ width: 1200px; color: var(--ink); font-family: {_FONT_STACK};
  -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; padding: 44px 40px; }}
.sheet {{ width: 1120px; margin: 0 auto; background: var(--card); border-radius: 24px; overflow: hidden;
  border: 1px solid #eceef3; box-shadow: 0 1px 2px rgba(20,24,29,.05), 0 28px 64px -28px rgba(20,24,29,.28); }}
.top {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 28px;
  padding: 38px 42px 24px; border-bottom: 1px solid var(--line); background: linear-gradient(180deg,#fbfcfe,#ffffff); }}
.identity {{ min-width: 0; }}
.eyebrow {{ font-size: 13px; font-weight: 700; color: var(--muted); letter-spacing: .02em; margin-bottom: 8px; }}
h1 {{ margin: 0; font-size: 38px; font-weight: 700; line-height: 1.1; letter-spacing: -.025em; }}
h1::after {{ content: ""; display: block; width: 46px; height: 4px; border-radius: 999px; background: var(--accent); margin-top: 13px; }}
.meta {{ margin-top: 13px; font-size: 15px; color: var(--muted); font-weight: 500; letter-spacing: -.01em; }}
.brandtag {{ display: flex; flex-direction: column; align-items: flex-end; gap: 9px; flex: none; }}
.brandtag .stamp {{ height: 52px; width: auto; opacity: .96; }}
.brandtag .logo-text {{ font-size: 30px; font-weight: 800; color: #c0392b; border: 3px solid #c0392b; border-radius: 11px; padding: 6px 14px; }}
.brandtag .txt {{ text-align: right; font-size: 11.5px; color: #aab0bd; font-weight: 600; line-height: 1.5; }}
.brandtag .txt b {{ color: var(--ink); font-weight: 700; display: block; font-size: 14px; letter-spacing: -.01em; }}
.body {{ padding: 24px 42px 30px; }}
.calendar {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 9px; }}
.weekday {{ text-align: center; font-size: 12.5px; font-weight: 700; color: var(--muted); letter-spacing: .01em; padding-bottom: 4px; }}
.day {{ min-height: 112px; padding: 11px; border: 1px solid var(--line); border-radius: 14px; background: #fcfdff; overflow: hidden; display: flex; flex-direction: column; }}
.day.out {{ opacity: .35; background: var(--row-alt); }}
.num {{ font-size: 16px; font-weight: 700; color: var(--ink-soft); font-variant-numeric: tabular-nums; }}
.badge {{ margin-top: auto; min-height: 30px; border-radius: 999px; display: inline-flex; align-items: center; align-self: flex-start; gap: 6px; padding: 0 12px; font-size: 14px; font-weight: 700; }}
.heart {{ font-size: 16px; line-height: 1; }}
.slot {{ width: 100%; margin-top: 7px; text-align: right; white-space: nowrap; font-size: 12px; line-height: 1.1; font-weight: 600; color: var(--muted); }}
.present {{ background: #e4f6ef; color: #0a8f6a; }}
.late {{ background: #fdf3da; color: #9a6a00; }}
.absent {{ background: #fdecea; color: #c0392b; }}
.unchecked {{ background: #eef0f4; color: #5b6472; }}
.excused {{ background: #e9ecff; color: #3a4ba0; }}
.makeup {{ background: #eaf1ff; color: #2f6df6; }}
.makeup .heart {{ color: #2f6df6; }}
.footer {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 24px; }}
.stat {{ border: 1px solid var(--line); border-radius: 14px; padding: 18px; background: #fcfdff; text-align: center; }}
.stat.present {{ background: #e4f6ef; border-color: transparent; }}
.stat.late {{ background: #fdf3da; border-color: transparent; }}
.stat.absent {{ background: #fdecea; border-color: transparent; }}
.stat.unchecked {{ background: #eef0f4; border-color: transparent; }}
.stat b {{ display: block; font-size: 34px; font-weight: 700; line-height: 1; margin-bottom: 6px; font-variant-numeric: tabular-nums; }}
.stat span {{ font-size: 13.5px; color: var(--muted); font-weight: 600; }}
.absence-note {{ margin-top: 18px; border: 1px solid var(--line); border-radius: 14px; background: #fcfdff; padding: 18px 20px; }}
.absence-note h2 {{ margin: 0 0 12px; font-size: 15px; font-weight: 700; color: var(--ink-soft); }}
.absence-list {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px 16px; }}
.absence-item {{ min-width: 0; font-size: 14px; line-height: 1.4; color: var(--ink-soft); font-weight: 500; }}
.absence-item b {{ color: #c0392b; font-weight: 700; margin-right: 9px; white-space: nowrap; }}
</style>
</head>
<body>
  <main class="sheet">
    <section class="top">
      <div class="identity">
        <div class="eyebrow">{month} 출석 달력</div>
        <h1>{name}</h1>
        <div class="meta">{school} · {period}</div>
      </div>
      {brand}
    </section>
    <div class="body">
      <section class="calendar">
        {"".join(f"<div class='weekday'>{day}</div>" for day in WEEKDAYS)}
        {cells}
      </section>
      <section class="footer">{stats}</section>
      {absences}
    </div>
  </main>
</body>
</html>"""


def calendar_image_height(payload: dict[str, Any]) -> int:
    reference_day = _parse_day(str(payload.get("today") or "")) or date.today()
    start_day = _parse_day(str(payload.get("start_date") or ""))
    end_day = _parse_day(str(payload.get("end_date") or ""))
    weeks = max(1, len(_calendar_days(start_day, end_day)) // 7)
    absence_count = len(_absence_notes(_attendance_rows(payload, reference_day)))
    note_rows = (absence_count + 1) // 2
    return 470 + weeks * 121 + (96 + max(0, note_rows - 1) * 26 if absence_count else 0)


def _calendar_cell(day: date, row: dict[str, Any] | None, start_day: date, end_day: date) -> str:
    out = " out" if day < start_day or day > end_day else ""
    status = str((row or {}).get("status") or "")
    if not row or status == "no_class":
        return f"<div class='day{out}'><div class='num'>{day.day}</div></div>"
    label = escape(STATUS_LABELS.get(status, status))
    css = escape(STATUS_CLASSES.get(status, "unchecked"))
    slot = escape(_slot_label(str(row.get("time_slot") or "")))
    heart = "<span class='heart'>&hearts;</span>" if status in {"present", "makeup"} else ""
    slot_html = f"<div class='slot'>{slot}</div>" if slot else ""
    return f"<div class='day{out}'><div class='num'>{day.day}</div><div class='badge {css}'>{heart}{label}</div>{slot_html}</div>"


def _attendance_rows(payload: dict[str, Any], today: date) -> dict[str, dict[str, Any]]:
    rows = payload.get("attendance")
    if not isinstance(rows, list):
        return {}
    visible: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        day_text = str(row.get("date") or "")[:10]
        day = _parse_day(day_text)
        status = str(row.get("status") or "")
        if status == "upcoming" or (status == "unchecked" and day > today):
            continue
        visible[day_text] = row
    return visible


def _display_summary(payload: dict[str, Any], rows: dict[str, dict[str, Any]]) -> dict[str, int]:
    source = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    summary = {key: _to_int(source.get(key)) for key, _ in _summary_order()}
    future_unchecked = 0
    raw_rows = payload.get("attendance")
    if isinstance(raw_rows, list):
        visible_dates = set(rows)
        future_unchecked = sum(
            1
            for row in raw_rows
            if isinstance(row, dict)
            and str(row.get("status") or "") == "unchecked"
            and str(row.get("date") or "")[:10] not in visible_dates
        )
    summary["unchecked"] = max(0, summary["unchecked"] - future_unchecked)
    return summary


def _calendar_days(start_day: date, end_day: date) -> list[date]:
    first = start_day - timedelta(days=start_day.weekday())
    last = end_day + timedelta(days=6 - end_day.weekday())
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def _stat(label: str, value: Any, key: str) -> str:
    return f"<div class='stat {escape(key)}'><b>{escape(str(value))}</b><span>{escape(label)}</span></div>"


def _summary_order() -> tuple[tuple[str, str], ...]:
    return (("present", "출석"), ("late", "지각"), ("absent", "결석"), ("unchecked", "미체크"))


def _absence_note_html(rows: dict[str, dict[str, Any]]) -> str:
    notes = _absence_notes(rows)
    if not notes:
        return ""
    items = "\n".join(
        f"<div class='absence-item'><b>{escape(day_label)}</b>{escape(reason)}</div>" for day_label, reason in notes
    )
    return f"<section class='absence-note'><h2>결석 사유</h2><div class='absence-list'>{items}</div></section>"


def _absence_notes(rows: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    notes: list[tuple[str, str]] = []
    for day_text, row in sorted(rows.items()):
        if str(row.get("status") or "") != "absent":
            continue
        day = _parse_day(day_text)
        reason = str(row.get("absence_reason") or row.get("notes") or "").strip() or "사유 미입력"
        notes.append((f"{day.month:02d}/{day.day:02d} {WEEKDAYS[day.weekday()]}", reason))
    return notes


def _profile_text(student: dict[str, Any]) -> str:
    parts = [str(student.get("school") or "").strip(), str(student.get("grade") or "").strip()]
    return " · ".join(part for part in parts if part) or "학생"


def _slot_label(value: str) -> str:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        return ""
    return " · ".join(SLOT_LABELS.get(part, part) for part in parts)


def _period_label(start_day: date, end_day: date) -> str:
    return f"{start_day.isoformat()} ~ {end_day.isoformat()}"


def _month_label(start_day: date, end_day: date) -> str:
    if start_day.year == end_day.year and start_day.month == end_day.month:
        return f"{start_day.year}년 {start_day.month}월"
    return f"{start_day.year}.{start_day.month} ~ {end_day.year}.{end_day.month}"


def _brand_html(logo_path: Path | None) -> str:
    logo_src = academy_brand_logo_src(logo_path)
    stamp = (
        f"<img class='stamp' src='{escape(logo_src, quote=True)}' alt='stamp'>"
        if logo_src
        else "<div class='logo-text'>MAX</div>"
    )
    return f"<div class='brandtag'>{stamp}<div class='txt'><b>Miho AI</b>PACA / Peak</div></div>"


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return date.today()


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
