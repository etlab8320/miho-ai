"""HTML template for YouTube summary cards."""

from __future__ import annotations

import html

from .models import SummaryResult


def render_card_html(summary: SummaryResult, *, font_css: str = "") -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>{html.escape(summary.short_title)}</title>
<style>
{font_css}
:root {{
  --paper: #fffaf1;
  --panel: #fffdf8;
  --ink: #171716;
  --muted: #69645c;
  --red: #d71920;
  --deep: #7f1518;
  --line: #e7d9bf;
  --soft: #f4ead8;
  --wash: #fff4e1;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: var(--paper); }}
body {{
  width: 1200px;
  padding: 38px;
  color: var(--ink);
  font-family: 'GoyangDeogyang', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
  letter-spacing: 0;
}}
.note-shell {{
  border: 5px solid var(--red);
  border-radius: 28px;
  padding: 18px;
  background:
    linear-gradient(90deg, rgba(215,25,32,.12) 0 1px, transparent 1px 100%),
    linear-gradient(180deg, var(--panel), var(--paper));
  background-size: 34px 34px, auto;
}}
.card {{
  border: 2px solid var(--line);
  border-radius: 20px;
  padding: 36px 40px 32px;
  background: rgba(255,253,248,.94);
}}
.top {{ display: grid; grid-template-columns: minmax(0, 1fr) 420px; gap: 30px; align-items: flex-start; }}
.label {{ display: inline-flex; align-items: center; gap: 10px; color: var(--red); font-size: 21px; font-weight: 800; }}
.label::before {{ content: ""; width: 34px; height: 10px; border-radius: 999px; background: var(--red); display: inline-block; }}
h1 {{
  margin: 12px 0 0;
  font-size: 62px;
  line-height: 1.02;
  color: var(--red);
  word-break: keep-all;
  overflow-wrap: anywhere;
}}
.source {{
  color: var(--muted);
  font-size: 20px;
  line-height: 1.45;
  text-align: right;
  word-break: keep-all;
  overflow-wrap: normal;
}}
.source strong {{ display: block; color: var(--deep); font-size: 24px; margin-bottom: 8px; }}
.topic {{
  margin: 28px 0 22px;
  padding: 18px 22px 18px 28px;
  border: 2px solid var(--line);
  border-left: 12px solid var(--red);
  border-radius: 16px;
  background: var(--wash);
  font-size: 25px;
  line-height: 1.45;
}}
.signal-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 0 0 22px; }}
.signal {{
  border: 1.5px solid var(--line);
  border-radius: 14px;
  background: white;
  padding: 12px 16px;
  min-height: 74px;
}}
.signal span {{ display: block; color: var(--muted); font-size: 16px; margin-bottom: 5px; }}
.signal strong {{ display: block; color: var(--deep); font-size: 24px; line-height: 1.15; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }}
.section {{
  border: 2px solid var(--line);
  border-radius: 18px;
  background: white;
  padding: 22px 24px;
}}
.section.wide {{ grid-column: 1 / -1; }}
h2 {{ margin: 0 0 14px; font-size: 27px; color: var(--red); line-height: 1.2; border-bottom: 2px solid var(--soft); padding-bottom: 10px; }}
ul {{ margin: 0; padding-left: 24px; }}
li {{ margin: 0 0 10px; font-size: 23px; line-height: 1.42; word-break: keep-all; overflow-wrap: anywhere; }}
.tags {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 24px; }}
.tag {{ border: 1.5px solid var(--red); color: var(--red); background: #fff; padding: 7px 13px; border-radius: 999px; font-size: 18px; }}
.foot {{ margin-top: 28px; color: var(--muted); font-size: 17px; display: flex; justify-content: space-between; gap: 16px; }}
</style>
</head>
<body>
<main class="note-shell">
<section class="card">
  <div class="top">
    <div>
      <div class="label">MIHO YOUTUBE NOTE</div>
      <h1>{html.escape(summary.short_title)}</h1>
    </div>
    <div class="source">
      <strong>{html.escape(summary.metadata.channel or "채널 확인 불가")}</strong>
      <div>{html.escape(summary.metadata.title or "원본 제목 확인 불가")}</div>
    </div>
  </div>
  <div class="topic">{html.escape(summary.topic)}</div>
  <div class="signal-row">
    <div class="signal"><span>분석 기준</span><strong>전체 자막</strong></div>
    <div class="signal"><span>세그먼트</span><strong>{int(summary.coverage.get("segment_count") or 0)}개</strong></div>
    <div class="signal"><span>저장 키</span><strong>{html.escape(summary.video_id)}</strong></div>
  </div>
  <div class="grid">
    {_section("요약 3줄", summary.summary_lines)}
    {_section("중요 포인트", summary.important_points)}
    {_section("교훈", summary.lessons, wide=True)}
    {_section("적용 아이디어", summary.practical_takeaways, wide=True)}
  </div>
  <div class="tags">{''.join(f'<span class="tag">#{html.escape(tag)}</span>' for tag in summary.tags[:8])}</div>
  <div class="foot">
    <span>근거: 전체 자막 {int(summary.coverage.get("segment_count") or 0)}개 세그먼트</span>
    <span>{html.escape(summary.video_id)}</span>
  </div>
</section>
</main>
<script>
document.documentElement.setAttribute(
  'data-render-height',
  String(Math.ceil(document.body.getBoundingClientRect().height))
);
</script>
</body>
</html>"""


def _section(title: str, items: list[str], *, wide: bool = False) -> str:
    if not items:
        return ""
    cls = "section wide" if wide else "section"
    body = "".join(f"<li>{html.escape(item)}</li>" for item in items[:8])
    return f'<section class="{cls}"><h2>{html.escape(title)}</h2><ul>{body}</ul></section>'
