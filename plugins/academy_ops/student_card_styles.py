"""CSS for academy student-card image rendering."""

from __future__ import annotations


def student_card_css() -> str:
    return """
* { box-sizing: border-box; }
html, body {
  width: 1200px;
  height: 1340px;
  margin: 0;
  overflow: hidden;
  background:
    radial-gradient(circle at 12% 8%, rgb(234 241 255 / .7), transparent 34%),
    radial-gradient(circle at 92% 0%, rgb(228 246 239 / .8), transparent 30%),
    #eef0f4;
  color: #16181d;
  font-family: "PretendardLocal", "GoyangDeogyang", "Pretendard", "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", sans-serif;
  letter-spacing: 0;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
.card {
  width: 1120px;
  height: 1260px;
  margin: 40px;
  padding: 34px;
  border: 1px solid #eceef3;
  border-radius: 24px;
  background: #ffffff;
  box-shadow: 0 1px 2px rgb(20 24 29 / .05), 0 28px 64px -28px rgb(20 24 29 / .28);
  overflow: hidden;
}
.layout { height: 100%; display: grid; grid-template-rows: 250px 154px 282px minmax(0, 452px); gap: 18px; }
.hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 250px;
  gap: 24px;
  min-width: 0;
  padding: 28px;
  border: 1px solid rgb(255 255 255 / .1);
  border-radius: 20px;
  background:
    radial-gradient(circle at 18% 0%, rgb(90 126 255 / .34), transparent 34%),
    radial-gradient(circle at 94% 15%, rgb(227 27 35 / .18), transparent 30%),
    linear-gradient(112deg, #101828 0 68%, #e31b23 68% 69.4%, #283142 69.4% 100%);
  color: #fffaf0;
  overflow: hidden;
}
.hero::after {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgb(255 255 255 / .08), transparent 48%);
  pointer-events: none;
}
.hero > * { position: relative; z-index: 1; }
.hero-copy { min-width: 0; }
.eyebrow { margin-bottom: 16px; color: #ffcc66; font-size: 21px; }
h1 { margin: 0 0 18px; font-size: 92px; line-height: .86; font-weight: 700; letter-spacing: -.02em; }
.meta { display: flex; flex-wrap: wrap; gap: 9px; max-width: 690px; }
.chip {
  min-height: 34px;
  padding: 7px 13px;
  border-radius: 999px;
  background: rgb(255 255 255 / .12);
  border: 1px solid rgb(255 255 255 / .12);
  color: #f8fafc;
  font-size: 18px;
}
.brand-stack { display: grid; grid-template-rows: 1fr 78px; gap: 16px; min-width: 0; }
.risk {
  display: grid;
  place-items: center;
  border: 1px solid rgb(255 255 255 / .38);
  border-radius: 16px;
  background: rgb(255 255 255 / .9);
  color: #101828;
  text-align: center;
  box-shadow: 0 16px 34px rgb(16 24 40 / .2);
}
.risk.caution { color: #8a4b00; }
.risk.danger { color: #b42318; }
.risk span { display: block; font-size: 18px; opacity: .86; }
.risk strong { display: block; margin-top: 7px; font-size: 50px; line-height: .9; }
.logo { width: 100%; height: 78px; object-fit: contain; object-position: right center; filter: saturate(1.05); }
.logo-fallback {
  display: grid;
  place-items: center;
  width: 100%;
  height: 78px;
  border: 4px solid oklch(68% 0.19 28);
  border-radius: 13px;
  color: oklch(68% 0.19 28);
  font-size: 42px;
}
.judgment {
  display: grid;
  grid-template-columns: 128px minmax(0, 1fr);
  gap: 20px;
  padding: 22px 26px;
  border-radius: 18px;
  background: #111827;
  color: #fffaf0;
}
.judgment-label {
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: rgb(255 255 255 / .1);
  color: #ffcc66;
  font-size: 22px;
}
.judgment-copy {
  display: flex;
  align-items: center;
  min-width: 0;
  font-size: 28px;
  line-height: 1.25;
  text-wrap: pretty;
}
.top-grid { display: grid; grid-template-columns: 1.08fr .92fr; gap: 18px; }
.lower-grid { display: grid; grid-template-columns: 1.12fr .88fr; gap: 18px; }
.panel {
  min-width: 0;
  border: 1px solid #e6e9ef;
  border-radius: 18px;
  padding: 22px 24px;
  background: #fcfdff;
  overflow: hidden;
}
.section-title { margin: 0 0 16px; font-size: 29px; line-height: 1; }
.title-note {
  margin-left: 8px;
  padding: 4px 9px;
  border-radius: 999px;
  background: oklch(93% 0.04 185);
  color: oklch(43% 0.055 205);
  font-size: 15px;
}
.attendance-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.metric {
  height: 96px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 8px;
  border-radius: 15px;
  background: #e4f6ef;
  text-align: center;
}
.metric b { display: block; font-size: 40px; line-height: .92; font-variant-numeric: tabular-nums; }
.metric span { display: block; color: #717784; font-size: 17px; line-height: 1; }
.today {
  margin-top: 14px;
  padding: 13px 15px;
  border-radius: 14px;
  background: #111827;
  color: #fffaf0;
  font-size: 22px;
}
.absence-strip { margin-top: 10px; display: flex; align-items: center; gap: 8px; min-height: 34px; font-size: 15px; }
.absence-label { color: #d92d20; font-size: 16px; }
.absence-days { display: flex; flex-wrap: wrap; gap: 6px; }
.absence-chip { padding: 5px 8px; border-radius: 999px; background: #fee4e2; color: #912018; }
ul { margin: 0; padding-left: 24px; }
li { margin: 0 0 12px; font-size: 22px; line-height: 1.28; }
.action-title { margin: 18px 0 8px; color: oklch(48% 0.12 31); font-size: 18px; }
.action-list { display: flex; flex-wrap: wrap; gap: 7px; }
.action-chip {
  padding: 7px 10px;
  border-radius: 999px;
  background: #fff1f0;
  color: #912018;
  font-size: 16px;
  line-height: 1.18;
}
.records { display: grid; gap: 8px; }
.record {
  min-height: 80px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 206px;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 15px;
  background: #eef6ff;
}
.record-line { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.record-name {
  color: #075985;
  font-size: 18px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.record-value { color: #111827; font-size: 23px; white-space: nowrap; }
.record-sub {
  margin-top: 6px;
  color: #667085;
  font-size: 15px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.record-sub b { color: #111827; }
.record-graph {
  height: 58px;
  display: flex;
  align-items: end;
  justify-content: end;
  gap: 6px;
  padding: 8px;
  border-radius: 12px;
  background: #ffffff;
}
.graph-bar { width: 15px; min-height: 12px; border-radius: 999px 999px 4px 4px; background: #9cc8da; }
.graph-bar.latest { background: #06aed5; }
.delta { color: #667085; }
.delta.up { color: oklch(47% 0.12 148); }
.delta.down { color: oklch(54% 0.15 31); }
.note-list { display: grid; gap: 9px; }
.note-item { padding: 12px 13px; border-radius: 14px; background: #f6f4ee; }
.note-date { margin-bottom: 5px; color: #667085; font-size: 15px; }
.note-text { font-size: 20px; line-height: 1.26; }
.empty { color: #667085; font-size: 22px; padding: 14px 0; }
"""
