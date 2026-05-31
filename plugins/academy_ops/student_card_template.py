"""HTML template for rich academy student-card images."""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

from .brand_assets import academy_brand_logo_src
from .report_fonts import report_font_css
from .student_card import RecordItem, StudentCard
from .student_card_fonts import goyang_font_css
from .student_card_styles import student_card_css


def render_student_card_html(card: StudentCard, *, logo_path: Path | None = None) -> str:
    profile = card.profile
    attendance = card.attendance
    total_marked = sum(attendance.summary.values())
    present_like = attendance.summary["present"] + attendance.summary["late"]
    attendance_rate = round((present_like / total_marked) * 100) if total_marked else 0
    visible_records = card.records[:3]
    records_html = "\n".join(_record_card(item) for item in visible_records)
    extra_records = len(card.records) - len(visible_records)
    record_note = f"<span class='title-note'>외 {extra_records}개</span>" if extra_records > 0 else ""
    if not records_html:
        records_html = "<div class='empty'>아직 연결된 Peak 기록이 없어.</div>"
    absences_html = _absence_days(attendance.recent_absences)
    notes_html = _consultation_notes(card.consultation_notes)
    risk_class = escape(card.risk.level or "stable")
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
{report_font_css()}
{goyang_font_css()}
{student_card_css()}
</style>
</head>
<body>
<main class="card">
  <div class="layout">
    <section class="hero">
      <div class="hero-copy">
        <div class="eyebrow">PACA / Peak 학생 운영 카드</div>
        <h1>{escape(profile.name)}</h1>
        <div class="meta">
          {_chip(profile.school or "학교 미기록")}
          {_chip(profile.grade or "학년 미기록")}
          {_chip(_slot_label(profile.time_slot))}
          {_chip(_weekly_label(profile.weekly_count))}
          {_chip(_status_label(profile.status))}
        </div>
      </div>
      <div class="brand-stack">
        <aside class="risk {risk_class}">
          <div><span>현재 판단</span><strong>{escape(_risk_label(card.risk.level))}</strong></div>
        </aside>
        {_logo_html(logo_path)}
      </div>
    </section>
    <section class="judgment">
      <div class="judgment-label">종합 판단</div>
      <div class="judgment-copy">{escape(card.risk.judgment)}</div>
    </section>
    <section class="top-grid">
      <div class="panel">
        <h2 class="section-title">최근 2주 출결</h2>
        <div class="attendance-row">
          {_metric("출석", str(attendance.summary["present"]))}
          {_metric("지각", str(attendance.summary["late"]))}
          {_metric("결석", str(attendance.summary["absent"]))}
          {_metric("등원률", f"{attendance_rate}%")}
        </div>
        <div class="today">오늘 상태: {escape(_attendance_label(attendance.today_status))}</div>
        <div class="absence-strip">
          <span class="absence-label">결석일</span><div class="absence-days">{absences_html}</div>
        </div>
      </div>
      <div class="panel">
        <h2 class="section-title">상담 포인트</h2>
        <ul>{_list_items(card.risk.reasons[:4])}</ul>
        <div class="action-title">다음 액션</div>
        <div class="action-list">{_action_items(card.risk.recommended_actions[:3])}</div>
      </div>
    </section>
    <section class="lower-grid">
      <div class="panel">
        <h2 class="section-title">최근 기록 {record_note}</h2>
        <div class="records">{records_html}</div>
      </div>
      <div class="panel">
        <h2 class="section-title">상담 기록</h2>
        {notes_html}
      </div>
    </section>
  </div>
</main>
</body>
</html>"""


def _record_card(item: RecordItem) -> str:
    delta = "변화 없음" if item.delta is None else f"{item.delta:+g}{item.unit}"
    trend_class = "up" if item.trend == "up" else "down" if item.trend == "down" else ""
    avg = item.average if item.average is not None else item.latest
    return (
        "<article class='record'>"
        "<div>"
        "<div class='record-line'>"
        f"<span class='record-name'>{escape(item.event_name)}</span>"
        f"<span class='record-value'>최근 {item.latest:g}{escape(item.unit)}</span>"
        "</div>"
        f"<div class='record-sub'>{escape(item.measured_at)} · PB <b>{item.best:g}</b>{escape(item.unit)} · "
        f"AVG <b>{avg:g}</b>{escape(item.unit)} · <span class='delta {trend_class}'>{escape(delta)}</span></div>"
        "</div>"
        f"<div class='record-graph'>{_record_graph(item)}</div>"
        "</article>"
    )


def _consultation_notes(notes: list[dict[str, str]]) -> str:
    if not notes:
        return "<div class='empty'>아직 저장된 상담 기록이 없어.</div>"
    rows = []
    for note in notes[:3]:
        day = escape(_date_weekday(str(note.get("consulted_at") or note.get("created_at") or "")))
        text = escape(str(note.get("note") or ""))
        rows.append(
            f"<article class='note-item'><div class='note-date'>{day}</div>"
            f"<div class='note-text'>{text}</div></article>"
        )
    return f"<div class='note-list'>{''.join(rows)}</div>"


def _list_items(items: list[str]) -> str:
    if not items:
        return "<li>확인된 상담 포인트가 아직 없어.</li>"
    return "\n".join(f"<li>{escape(item)}</li>" for item in items)


def _action_items(items: list[str]) -> str:
    if not items:
        return "<span class='action-chip'>추가 확인 없음</span>"
    return "".join(f"<span class='action-chip'>{escape(item)}</span>" for item in items)


def _chip(text: str) -> str:
    return f"<span class='chip'>{escape(text)}</span>"


def _metric(label: str, value: str) -> str:
    return f"<div class='metric'><span>{escape(label)}</span><b>{escape(value)}</b></div>"


def _absence_days(days: list[str]) -> str:
    if not days:
        return "<span class='absence-chip'>최근 없음</span>"
    return "".join(f"<span class='absence-chip'>{escape(_date_weekday(day))}</span>" for day in days[-4:])


def _date_weekday(value: str) -> str:
    try:
        day = date.fromisoformat(value[:10])
    except ValueError:
        return value
    weekdays = ("월", "화", "수", "목", "금", "토", "일")
    return f"{day.month:02d}.{day.day:02d} {weekdays[day.weekday()]}"


def _record_graph(item: RecordItem) -> str:
    samples = item.samples or (item.latest,)
    low = min(samples)
    high = max(samples)
    spread = high - low
    bars = []
    for index, value in enumerate(samples):
        ratio = 0.5 if spread == 0 else (value - low) / spread
        height = 18 + round(ratio * 42)
        latest_class = " latest" if index == len(samples) - 1 else ""
        bars.append(f"<span class='graph-bar{latest_class}' style='height:{height}px'></span>")
    return "".join(bars)


def _logo_html(logo_path: Path | None) -> str:
    logo_src = academy_brand_logo_src(logo_path)
    if logo_src:
        return f"<img class='logo' src='{escape(logo_src, quote=True)}' alt='MAX'>"
    return "<div class='logo-fallback'>MAX</div>"


def _risk_label(level: str) -> str:
    return {"stable": "안정", "caution": "주의", "danger": "위험"}.get(level, "확인")


def _attendance_label(status: str) -> str:
    return {"present": "출석", "late": "지각", "absent": "결석", "unknown": "미확인"}.get(status, status or "미확인")


def _slot_label(slot: str) -> str:
    if not slot:
        return "시간대 미기록"
    return {"morning": "오전", "afternoon": "오후", "evening": "저녁"}.get(slot, slot)


def _weekly_label(weekly_count: int | None) -> str:
    return f"주 {weekly_count}회" if weekly_count else "주 횟수 미기록"


def _status_label(status: str) -> str:
    return {"active": "재원", "inactive": "휴원"}.get(status, status or "상태 미기록")
