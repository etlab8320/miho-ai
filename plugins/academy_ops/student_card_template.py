"""HTML template for rich academy student-card images."""

from __future__ import annotations

from html import escape

from .student_card import RecordItem, StudentCard
from .student_card_fonts import GOYANG_LICENSE_NOTE, goyang_font_css


def render_student_card_html(card: StudentCard) -> str:
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
    missing = " · ".join(card.missing_sources) if card.missing_sources else "PACA/Peak 조회 정상"
    actions = "\n".join(f"<li>{escape(action)}</li>" for action in card.risk.recommended_actions[:3])
    reasons = "\n".join(f"<li>{escape(reason)}</li>" for reason in card.risk.reasons[:4])
    risk_class = escape(card.risk.level or "stable")
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
{goyang_font_css()}
:root {{
  --canvas: oklch(94% 0.012 223);
  --paper: oklch(98.8% 0.004 220);
  --ink: oklch(22% 0.035 248);
  --muted: oklch(55% 0.025 245);
  --line: oklch(86% 0.012 232);
  --panel: oklch(96.8% 0.009 226);
  --teal: oklch(55% 0.12 185);
  --teal-soft: oklch(91% 0.035 185);
  --coral: oklch(60% 0.17 31);
  --amber: oklch(78% 0.13 78);
  --green: oklch(58% 0.12 148);
}}
* {{ box-sizing: border-box; }}
html, body {{
  width: 1200px;
  height: 1400px;
  margin: 0;
  overflow: hidden;
  background:
    linear-gradient(135deg, oklch(92% 0.018 190), transparent 42%),
    linear-gradient(315deg, oklch(95% 0.016 32), var(--canvas));
  color: var(--ink);
  font-family: "GoyangDeogyang", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  letter-spacing: 0;
}}
.card {{
  width: 1120px;
  height: 1320px;
  margin: 40px;
  padding: 44px;
  border: 1px solid oklch(82% 0.014 232);
  border-radius: 8px;
  background: var(--paper);
  box-shadow: 0 24px 80px oklch(25% 0.028 250 / .14);
  overflow: hidden;
}}
.layout {{
  height: 100%;
  display: grid;
  grid-template-rows: 246px 176px 292px 388px 46px;
  gap: 21px;
}}
.hero {{
  display: grid;
  grid-template-columns: 1fr 214px;
  gap: 28px;
  padding: 32px 34px;
  border-radius: 8px;
  background:
    linear-gradient(90deg, oklch(99% 0.006 220), oklch(94% 0.026 188)),
    var(--panel);
  border: 1px solid var(--line);
}}
.eyebrow {{
  margin-bottom: 13px;
  color: var(--teal);
  font-size: 23px;
}}
.identity {{
  display: flex;
  align-items: center;
  gap: 25px;
}}
.mark {{
  width: 126px;
  height: 126px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--ink);
  color: oklch(96% 0.009 220);
  font-size: 54px;
  font-weight: 700;
}}
h1 {{
  margin: 0 0 17px;
  font-size: 92px;
  line-height: .9;
  font-weight: 700;
}}
.meta {{
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  max-width: 720px;
}}
.chip {{
  min-height: 38px;
  padding: 8px 14px;
  border-radius: 999px;
  background: oklch(92% 0.018 226);
  color: oklch(35% 0.035 245);
  font-size: 20px;
}}
.risk {{
  display: grid;
  place-items: center;
  align-self: stretch;
  border-radius: 8px;
  background: var(--green);
  color: oklch(98% 0.004 220);
  text-align: center;
}}
.risk.caution {{ background: var(--amber); color: var(--ink); }}
.risk.danger {{ background: var(--coral); }}
.risk span {{ display: block; font-size: 20px; opacity: .86; }}
.risk strong {{ display: block; margin-top: 9px; font-size: 54px; line-height: .9; }}
.judgment {{
  display: grid;
  grid-template-columns: 132px minmax(0, 1fr);
  align-items: stretch;
  gap: 24px;
  padding: 24px 28px;
  border-radius: 8px;
  background: var(--ink);
  color: oklch(97% 0.006 220);
  overflow: hidden;
}}
.judgment-label {{
  display: grid;
  place-items: center;
  min-height: 100%;
  padding-right: 18px;
  border-right: 1px solid oklch(58% 0.055 194 / .45);
  color: oklch(82% 0.08 185);
  font-size: 23px;
  line-height: 1.12;
}}
.judgment-copy {{
  min-width: 0;
  display: flex;
  align-items: center;
  height: 100%;
  font-size: 28px;
  line-height: 1.25;
  text-wrap: pretty;
}}
.top-grid {{
  display: grid;
  grid-template-columns: 1.16fr .84fr;
  gap: 21px;
}}
.lower-grid {{
  display: grid;
  grid-template-columns: 1.03fr .97fr;
  gap: 21px;
}}
.panel {{
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 26px 28px;
  background: oklch(98% 0.006 226);
  overflow: hidden;
}}
.section-title {{
  margin: 0 0 20px;
  color: var(--ink);
  font-size: 30px;
  line-height: 1;
}}
.title-note {{
  margin-left: 8px;
  padding: 5px 9px;
  border-radius: 999px;
  background: var(--teal-soft);
  color: var(--muted);
  font-size: 16px;
  vertical-align: middle;
}}
.attendance-row {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}}
.metric {{
  height: 104px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 9px;
  padding: 12px;
  border-radius: 8px;
  background: var(--teal-soft);
  text-align: center;
}}
.metric b {{
  display: block;
  font-size: 43px;
  line-height: .92;
}}
.metric span {{
  display: block;
  color: var(--muted);
  font-size: 19px;
  line-height: 1;
}}
.today {{
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 8px;
  background: var(--paper);
  color: var(--ink);
  font-size: 23px;
}}
.absence-strip {{
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  color: var(--muted);
  font-size: 15px;
}}
.absence-label {{ color: var(--coral); font-size: 16px; }}
.absence-days {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}}
.absence-chip {{
  padding: 5px 8px;
  border-radius: 999px;
  background: oklch(96% 0.018 30);
  color: oklch(48% 0.08 30);
}}
ul {{ margin: 0; padding-left: 24px; }}
li {{ margin: 0 0 14px; font-size: 23px; line-height: 1.3; }}
.records {{
  display: grid;
  gap: 8px;
}}
.lower-grid .panel {{
  padding: 22px 28px;
}}
.lower-grid .section-title {{
  margin-bottom: 14px;
}}
.record {{
  min-height: 74px;
  display: grid;
  grid-template-columns: 1fr 214px;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: oklch(94% 0.02 205);
}}
.record-line {{
  display: flex;
  align-items: baseline;
  gap: 10px;
}}
.record-name {{
  color: oklch(35% 0.06 190);
  font-size: 18px;
  white-space: nowrap;
}}
.record-value {{
  color: var(--ink);
  font-size: 22px;
}}
.record-sub {{
  margin-top: 6px;
  color: var(--muted);
  font-size: 16px;
}}
.record-sub b {{ color: var(--ink); }}
.record-graph {{
  height: 58px;
  display: flex;
  align-items: end;
  justify-content: end;
  gap: 6px;
  padding: 8px;
  border-radius: 8px;
  background: oklch(98% 0.006 226);
}}
.graph-bar {{
  width: 15px;
  min-height: 12px;
  border-radius: 999px 999px 4px 4px;
  background: oklch(72% 0.045 205);
}}
.graph-bar.latest {{ background: var(--teal); }}
.delta {{
  color: var(--muted);
}}
.delta.up {{ color: var(--green); }}
.delta.down {{ color: var(--coral); }}
.empty {{
  color: var(--muted);
  font-size: 23px;
  padding: 18px 0;
}}
.source {{
  align-self: end;
  color: oklch(54% 0.025 246);
  font-size: 18px;
  line-height: 1.28;
}}
.source span {{
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
</style>
</head>
<body>
<main class="card">
  <div class="layout">
    <section class="hero">
      <div>
        <div class="eyebrow">PACA / Peak 학생 운영 카드</div>
        <div class="identity">
          <div class="mark">{escape(_initials(profile.name))}</div>
          <div>
            <h1>{escape(profile.name)}</h1>
            <div class="meta">
              {_chip(profile.school or "학교 미기록")}
              {_chip(profile.grade or "학년 미기록")}
              {_chip(_slot_label(profile.time_slot))}
              {_chip(_weekly_label(profile.weekly_count))}
              {_chip(_status_label(profile.status))}
            </div>
          </div>
        </div>
      </div>
      <aside class="risk {risk_class}"><div><span>현재 판단</span><strong>{escape(_risk_label(card.risk.level))}</strong></div></aside>
    </section>
    <section class="judgment">
      <div class="judgment-label">종합 판단</div>
      <div class="judgment-copy">{escape(card.risk.judgment)}</div>
    </section>
    <section class="top-grid">
      <div class="panel">
        <h2 class="section-title">최근 출결</h2>
        <div class="attendance-row">
          {_metric("출석", str(attendance.summary["present"]))}
          {_metric("지각", str(attendance.summary["late"]))}
          {_metric("결석", str(attendance.summary["absent"]))}
          {_metric("등원률", f"{attendance_rate}%")}
        </div>
        <div class="today">오늘 상태: {escape(_attendance_label(attendance.today_status))}</div>
        <div class="absence-strip"><span class="absence-label">결석일</span><div class="absence-days">{absences_html}</div></div>
      </div>
      <div class="panel">
        <h2 class="section-title">상담 포인트</h2>
        <ul>{reasons}</ul>
      </div>
    </section>
    <section class="lower-grid">
      <div class="panel">
        <h2 class="section-title">최근 기록 {record_note}</h2>
        <div class="records">{records_html}</div>
      </div>
      <div class="panel">
        <h2 class="section-title">다음 액션</h2>
        <ul>{actions}</ul>
      </div>
    </section>
    <footer class="source">
      <span>자료 상태: {escape(missing)}</span>
      <span>민감정보 제외 완료 · {GOYANG_LICENSE_NOTE}</span>
    </footer>
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


def _chip(text: str) -> str:
    return f"<span class='chip'>{escape(text)}</span>"


def _metric(label: str, value: str) -> str:
    return f"<div class='metric'><span>{escape(label)}</span><b>{escape(value)}</b></div>"


def _absence_days(days: list[str]) -> str:
    if not days:
        return "<span class='absence-chip'>최근 없음</span>"
    return "".join(f"<span class='absence-chip'>{escape(_date_weekday(day))}</span>" for day in days[-4:])


def _date_weekday(value: str) -> str:
    from datetime import date

    try:
        day = date.fromisoformat(value)
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


def _initials(name: str) -> str:
    clean = name.strip()
    return clean[-2:] if len(clean) >= 2 else clean or "학생"


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
