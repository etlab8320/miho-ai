"""HTML template for student attendance calendar images."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape
from pathlib import Path
from typing import Any


STATUS_LABELS = {
    "present": "출석",
    "late": "지각",
    "absent": "결석",
    "unchecked": "미체크",
    "upcoming": "예정",
    "excused": "인정",
    "makeup": "보강",
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
    logo = _logo_html(logo_path)
    name = escape(str(student.get("name") or "학생"))
    school = escape(_profile_text(student))
    period = escape(_period_label(start_day, end_day))
    month = escape(_month_label(start_day, end_day))
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: #f7f5f0; color: #25211d; }}
body {{
  width: 1200px;
  min-height: 100vh;
  font-family: "Apple SD Gothic Neo", "Noto Sans KR", "Pretendard", sans-serif;
}}
.sheet {{ width: 1120px; margin: 40px auto; padding: 34px; background: #fffdf8; border: 1px solid #e5ded4; border-radius: 26px; }}
.top {{ display: flex; align-items: center; justify-content: space-between; gap: 28px; margin-bottom: 26px; }}
.identity {{ min-width: 0; }}
.eyebrow {{ font-size: 18px; font-weight: 800; color: #b71d25; letter-spacing: .02em; }}
h1 {{ margin: 8px 0 8px; font-size: 52px; line-height: 1.02; letter-spacing: 0; }}
.meta {{ font-size: 22px; color: #6b6258; font-weight: 700; }}
.logo {{ width: 244px; max-height: 104px; object-fit: contain; object-position: right center; }}
.logo-text {{ font-size: 46px; font-weight: 1000; color: #d11d28; border: 5px solid #d11d28; border-radius: 14px; padding: 10px 22px; }}
.calendar {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; }}
.weekday {{ text-align: center; font-size: 18px; font-weight: 900; color: #80766c; padding-bottom: 3px; }}
.day {{ min-height: 100px; padding: 12px; border: 1px solid #e8e0d5; border-radius: 16px; background: #fffcf7; position: relative; overflow: hidden; }}
.day.out {{ opacity: .32; }}
.num {{ font-size: 20px; font-weight: 900; color: #4f463d; }}
.badge {{ margin-top: 14px; min-height: 38px; border-radius: 999px; display: inline-flex; align-items: center; gap: 7px; padding: 0 13px; font-size: 17px; font-weight: 900; }}
.heart {{ font-size: 21px; line-height: 1; }}
.slot {{ position: absolute; right: 11px; bottom: 10px; font-size: 15px; font-weight: 800; color: #7f766d; }}
.present {{ background: #fee7e6; color: #c81e2b; }}
.late {{ background: #fff0c2; color: #80601a; }}
.absent {{ background: #ece7df; color: #5b5147; }}
.unchecked {{ background: #e7f0ee; color: #21675d; }}
.excused, .makeup {{ background: #e9ecff; color: #344187; }}
.footer {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-top: 24px; }}
.stat {{ border: 1px solid #e7dfd4; border-radius: 18px; padding: 17px 18px; background: #fdf8ef; text-align: center; }}
.stat b {{ display: block; font-size: 34px; line-height: 1; margin-bottom: 6px; }}
.stat span {{ font-size: 17px; color: #776d63; font-weight: 900; }}
.note {{ margin-top: 18px; font-size: 17px; color: #7e7469; font-weight: 700; }}
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
      {logo}
    </section>
    <section class="calendar">
      {"".join(f"<div class='weekday'>{day}</div>" for day in WEEKDAYS)}
      {cells}
    </section>
    <section class="footer">{stats}</section>
    <div class="note">수업없는 날과 아직 오지 않은 날은 별도 표시하지 않았어. 하트는 출석 처리된 수업일이야.</div>
  </main>
</body>
</html>"""


def calendar_image_height(payload: dict[str, Any]) -> int:
    start_day = _parse_day(str(payload.get("start_date") or ""))
    end_day = _parse_day(str(payload.get("end_date") or ""))
    weeks = max(1, len(_calendar_days(start_day, end_day)) // 7)
    return 430 + weeks * 112


def _calendar_cell(day: date, row: dict[str, Any] | None, start_day: date, end_day: date) -> str:
    out = " out" if day < start_day or day > end_day else ""
    status = str((row or {}).get("status") or "")
    if not row or status == "no_class":
        return f"<div class='day{out}'><div class='num'>{day.day}</div></div>"
    label = escape(STATUS_LABELS.get(status, status))
    css = escape(STATUS_CLASSES.get(status, "unchecked"))
    slot = escape(SLOT_LABELS.get(str(row.get("time_slot") or ""), str(row.get("time_slot") or "")))
    heart = "<span class='heart'>&hearts;</span>" if status == "present" else ""
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


def _profile_text(student: dict[str, Any]) -> str:
    parts = [str(student.get("school") or "").strip(), str(student.get("grade") or "").strip()]
    return " · ".join(part for part in parts if part) or "학생"


def _period_label(start_day: date, end_day: date) -> str:
    return f"{start_day.isoformat()} ~ {end_day.isoformat()}"


def _month_label(start_day: date, end_day: date) -> str:
    if start_day.year == end_day.year and start_day.month == end_day.month:
        return f"{start_day.year}년 {start_day.month}월"
    return f"{start_day.year}.{start_day.month} ~ {end_day.year}.{end_day.month}"


def _logo_html(logo_path: Path | None) -> str:
    if logo_path and logo_path.exists():
        return f"<img class='logo' src='{escape(logo_path.as_uri(), quote=True)}' alt='MAX'>"
    return "<div class='logo-text'>MAX</div>"


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
