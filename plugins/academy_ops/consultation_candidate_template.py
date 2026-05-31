"""HTML template for academy consultation candidate images."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from .brand_assets import academy_brand_logo_src
from .consultation_candidate_format import _priority_label
from .report_fonts import PRETENDARD_FAMILY, report_font_css

# Same Korean-first stack as report_design (bundled Pretendard first, then fallbacks).
_FONT_STACK = (
    f"'{PRETENDARD_FAMILY}','Goyang','GoyangDeogyang','Pretendard',"
    "'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif"
)
# Map the caller-supplied priority onto an accent tier (no domain literals).
_PRIORITY_CLASSES = {"high": "high", "medium": "medium", "low": "low"}


def render_consultation_candidates_html(payload: dict[str, Any], *, logo_path: Path | None = None) -> str:
    candidates = [item for item in payload.get("candidates") or [] if isinstance(item, dict)]
    period_days = int(payload.get("period_days") or 14)
    today = escape(str(payload.get("today") or ""))
    rows = "\n".join(_candidate_row(index, item) for index, item in enumerate(candidates[:10], start=1))
    brand = _brand_html(logo_path)
    empty = "<div class='empty'>이번 기준으로 우선 상담 후보는 없어.</div>" if not rows else ""
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
{report_font_css()}
:root {{
  --bg:#eef0f4;--card:#ffffff;--ink:#16181d;--ink-soft:#3a4150;--muted:#717784;
  --line:#e6e9ef;--line-soft:#f0f2f6;--neutral-soft:#eef0f4;--accent:#111827;
  --high:#c0392b;--high-soft:#fdecea;--medium:#9a6a00;--medium-soft:#fdf3da;
  --low:#0a8f6a;--low-soft:#e4f6ef;--rank:#5b6472;--rank-soft:#eef0f4;
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
.eyebrow {{ font-size: 13px; font-weight: 700; color: var(--muted); letter-spacing: .02em; margin-bottom: 8px; }}
.title {{ font-size: 38px; font-weight: 700; letter-spacing: -.025em; line-height: 1.1; }}
.title::after {{ content: ""; display: block; width: 46px; height: 4px; border-radius: 999px; background: var(--accent); margin-top: 13px; }}
.subtitle {{ margin-top: 13px; font-size: 15px; color: var(--muted); font-weight: 500; letter-spacing: -.01em; }}
.brandtag {{ display: flex; flex-direction: column; align-items: flex-end; gap: 9px; flex: none; }}
.brandtag .stamp {{ height: 52px; width: auto; opacity: .96; }}
.brandtag .logo-text {{ font-size: 30px; font-weight: 800; color: #c0392b; border: 3px solid #c0392b; border-radius: 11px; padding: 6px 14px; }}
.brandtag .txt {{ text-align: right; font-size: 11.5px; color: #aab0bd; font-weight: 600; line-height: 1.5; }}
.brandtag .txt b {{ color: var(--ink); font-weight: 700; display: block; font-size: 14px; letter-spacing: -.01em; }}
.body {{ padding: 22px 42px 30px; }}
.list {{ display: grid; gap: 12px; }}
.row {{ display: grid; grid-template-columns: 56px minmax(0, 228px) 132px 1fr; gap: 18px; align-items: center;
  padding: 18px 20px; border: 1px solid var(--line); border-radius: 16px; background: #fcfdff; }}
.rank {{ width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center;
  background: var(--rank-soft); color: var(--rank); font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.row.high .rank {{ background: var(--high-soft); color: var(--high); }}
.name {{ min-width: 0; font-size: 24px; font-weight: 700; color: var(--ink); letter-spacing: -.01em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.school {{ margin-top: 4px; font-size: 14px; font-weight: 500; color: var(--muted); }}
.priority {{ display: inline-flex; align-items: center; justify-content: center; min-height: 34px; border-radius: 999px;
  padding: 0 16px; background: var(--neutral-soft); color: var(--ink-soft); font-size: 14px; font-weight: 700; }}
.priority.high {{ background: var(--high-soft); color: var(--high); }}
.priority.medium {{ background: var(--medium-soft); color: var(--medium); }}
.priority.low {{ background: var(--low-soft); color: var(--low); }}
.reasons {{ min-width: 0; display: grid; gap: 6px; }}
.reason {{ position: relative; padding-left: 16px; font-size: 15.5px; line-height: 1.34; font-weight: 500; color: var(--ink-soft); }}
.reason::before {{ content: ""; position: absolute; left: 2px; top: 9px; width: 5px; height: 5px; border-radius: 999px; background: #c2c8d2; }}
.empty {{ min-height: 360px; display: grid; place-items: center; border: 1px dashed var(--line);
  border-radius: 16px; font-size: 22px; font-weight: 600; color: var(--muted); }}
</style>
</head>
<body>
  <main class="sheet">
    <section class="top">
      <div class="headline">
        <div class="eyebrow">상담 우선 후보</div>
        <div class="title">{len(candidates)}명 목록</div>
        <div class="subtitle">기준일 {today} · 최근 {period_days}일 출결/기록 신호</div>
      </div>
      {brand}
    </section>
    <div class="body">
      <section class="list">{rows}</section>
      {empty}
    </div>
  </main>
</body>
</html>"""


def consultation_candidates_image_height(payload: dict[str, Any]) -> int:
    count = len([item for item in payload.get("candidates") or [] if isinstance(item, dict)])
    return 360 + max(1, min(count, 10)) * 112


def _candidate_row(index: int, item: dict[str, Any]) -> str:
    student = item.get("student") if isinstance(item.get("student"), dict) else item
    name = escape(str(student.get("name") or item.get("name") or "이름 없음"))
    profile = escape(_profile_text(student))
    priority = escape(_priority_label(item.get("priority")) or "확인")
    priority_cls = _PRIORITY_CLASSES.get(str(item.get("priority") or "").strip().lower(), "")
    row_cls = " high" if priority_cls == "high" else ""
    priority_class = f" {priority_cls}" if priority_cls else ""
    reasons = [str(reason).strip() for reason in item.get("reasons") or [] if str(reason).strip()]
    reasons_html = "".join(f"<div class='reason'>{escape(reason)}</div>" for reason in reasons[:3])
    if not reasons_html:
        reasons_html = "<div class='reason'>상담 사유 데이터 없음</div>"
    return (
        f"<article class='row{row_cls}'>"
        f"<div class='rank'>{index}</div>"
        f"<div><div class='name'>{name}</div><div class='school'>{profile}</div></div>"
        f"<div class='priority{priority_class}'>우선순위 {priority}</div>"
        f"<div class='reasons'>{reasons_html}</div>"
        "</article>"
    )


def _profile_text(student: dict[str, Any]) -> str:
    parts = [str(student.get(key) or "").strip() for key in ("school", "grade")]
    return " · ".join(part for part in parts if part) or "프로필 확인 필요"


def _brand_html(path: Path | None) -> str:
    logo_src = academy_brand_logo_src(path)
    stamp = (
        f"<img class='stamp' src='{escape(logo_src, quote=True)}' alt='stamp'>"
        if logo_src
        else "<div class='logo-text'>MAX</div>"
    )
    return f"<div class='brandtag'>{stamp}<div class='txt'><b>Miho AI</b>PACA / Peak</div></div>"
