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
    radial-gradient(circle at 8% 8%, oklch(93% 0.035 30), transparent 30%),
    linear-gradient(145deg, oklch(94% 0.014 78), oklch(91% 0.018 210));
  color: oklch(20% 0.035 245);
  font-family: "GoyangDeogyang", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  letter-spacing: 0;
}
.card {
  width: 1120px;
  height: 1260px;
  margin: 40px;
  padding: 34px;
  border: 1px solid oklch(82% 0.018 74);
  border-radius: 22px;
  background: oklch(98.5% 0.007 82);
  box-shadow: 0 26px 80px oklch(24% 0.035 245 / .18);
  overflow: hidden;
}
.layout { height: 100%; display: grid; grid-template-rows: 246px 154px 278px 392px 40px; gap: 18px; }
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 250px;
  gap: 24px;
  min-width: 0;
  padding: 28px;
  border-radius: 18px;
  background:
    linear-gradient(112deg, oklch(24% 0.055 245) 0 55%, oklch(47% 0.12 28) 55% 100%);
  color: oklch(98% 0.008 82);
  overflow: hidden;
}
.hero-copy { min-width: 0; }
.eyebrow { margin-bottom: 16px; color: oklch(84% 0.13 78); font-size: 21px; }
h1 { margin: 0 0 18px; font-size: 92px; line-height: .86; font-weight: 700; }
.meta { display: flex; flex-wrap: wrap; gap: 9px; max-width: 690px; }
.chip {
  min-height: 34px;
  padding: 7px 13px;
  border-radius: 999px;
  background: oklch(98% 0.008 82 / .13);
  color: oklch(94% 0.014 82);
  font-size: 18px;
}
.brand-stack { display: grid; grid-template-rows: 1fr 78px; gap: 16px; min-width: 0; }
.risk {
  display: grid;
  place-items: center;
  border: 1px solid oklch(95% 0.01 82 / .26);
  border-radius: 16px;
  background: oklch(60% 0.13 148);
  text-align: center;
}
.risk.caution { background: oklch(78% 0.13 78); color: oklch(22% 0.04 80); }
.risk.danger { background: oklch(60% 0.18 31); }
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
  background: oklch(24% 0.035 245);
  color: oklch(97% 0.008 82);
}
.judgment-label {
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: oklch(34% 0.045 245);
  color: oklch(83% 0.12 78);
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
  border: 1px solid oklch(86% 0.018 78);
  border-radius: 18px;
  padding: 22px 24px;
  background: oklch(99% 0.005 82);
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
  background: oklch(94% 0.035 185);
  text-align: center;
}
.metric b { display: block; font-size: 40px; line-height: .92; }
.metric span { display: block; color: oklch(45% 0.035 210); font-size: 17px; line-height: 1; }
.today {
  margin-top: 14px;
  padding: 13px 15px;
  border-radius: 14px;
  background: oklch(25% 0.035 245);
  color: oklch(96% 0.008 82);
  font-size: 22px;
}
.absence-strip { margin-top: 10px; display: flex; align-items: center; gap: 8px; min-height: 34px; font-size: 15px; }
.absence-label { color: oklch(54% 0.15 31); font-size: 16px; }
.absence-days { display: flex; flex-wrap: wrap; gap: 6px; }
.absence-chip { padding: 5px 8px; border-radius: 999px; background: oklch(95% 0.026 31); color: oklch(45% 0.09 31); }
ul { margin: 0; padding-left: 24px; }
li { margin: 0 0 12px; font-size: 22px; line-height: 1.28; }
.action-title { margin: 18px 0 8px; color: oklch(48% 0.12 31); font-size: 18px; }
.action-list { display: flex; flex-wrap: wrap; gap: 7px; }
.action-chip {
  padding: 7px 10px;
  border-radius: 999px;
  background: oklch(94% 0.03 31);
  color: oklch(38% 0.08 31);
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
  background: oklch(95% 0.02 205);
}
.record-line { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.record-name {
  color: oklch(34% 0.065 190);
  font-size: 18px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.record-value { color: oklch(20% 0.035 245); font-size: 23px; white-space: nowrap; }
.record-sub {
  margin-top: 6px;
  color: oklch(52% 0.025 245);
  font-size: 15px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.record-sub b { color: oklch(22% 0.035 245); }
.record-graph {
  height: 58px;
  display: flex;
  align-items: end;
  justify-content: end;
  gap: 6px;
  padding: 8px;
  border-radius: 12px;
  background: oklch(99% 0.005 82);
}
.graph-bar { width: 15px; min-height: 12px; border-radius: 999px 999px 4px 4px; background: oklch(74% 0.05 205); }
.graph-bar.latest { background: oklch(55% 0.12 185); }
.delta { color: oklch(52% 0.025 245); }
.delta.up { color: oklch(47% 0.12 148); }
.delta.down { color: oklch(54% 0.15 31); }
.note-list { display: grid; gap: 9px; }
.note-item { padding: 12px 13px; border-radius: 14px; background: oklch(96% 0.015 78); }
.note-date { margin-bottom: 5px; color: oklch(50% 0.035 245); font-size: 15px; }
.note-text { font-size: 20px; line-height: 1.26; }
.empty { color: oklch(52% 0.025 245); font-size: 22px; padding: 14px 0; }
.source { align-self: end; color: oklch(54% 0.025 246); font-size: 17px; line-height: 1.24; }
.source span { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
"""
