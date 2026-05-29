"""HTML template for academy consultation candidate images."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from .consultation_candidate_format import _priority_label


def render_consultation_candidates_html(payload: dict[str, Any], *, logo_path: Path | None = None) -> str:
    candidates = [item for item in payload.get("candidates") or [] if isinstance(item, dict)]
    period_days = int(payload.get("period_days") or 14)
    today = escape(str(payload.get("today") or ""))
    rows = "\n".join(_candidate_row(index, item) for index, item in enumerate(candidates[:10], start=1))
    logo = _logo_html(logo_path)
    empty = "<div class='empty'>이번 기준으로 우선 상담 후보는 없어.</div>" if not rows else ""
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: #f5f2eb; color: #27231f; }}
body {{
  width: 1200px;
  min-height: 100vh;
  font-family: "Apple SD Gothic Neo", "Noto Sans KR", "Pretendard", sans-serif;
}}
.sheet {{ width: 1120px; margin: 40px auto; padding: 34px; background: #fffdf8; border: 1px solid #e4dacf; border-radius: 24px; }}
.top {{ display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 26px; }}
.eyebrow {{ font-size: 18px; font-weight: 900; color: #b71d25; }}
h1 {{ margin: 8px 0; font-size: 48px; line-height: 1.04; letter-spacing: 0; }}
.meta {{ font-size: 21px; color: #6c635a; font-weight: 800; }}
.logo {{ width: 226px; max-height: 96px; object-fit: contain; object-position: right center; }}
.logo-text {{ font-size: 42px; font-weight: 1000; color: #d11d28; border: 5px solid #d11d28; border-radius: 14px; padding: 9px 20px; }}
.list {{ display: grid; gap: 12px; }}
.row {{ display: grid; grid-template-columns: 76px minmax(0, 230px) 138px 1fr; gap: 16px; align-items: start; padding: 18px; border: 1px solid #e7ded2; border-radius: 18px; background: #fffbf3; }}
.rank {{ width: 48px; height: 48px; border-radius: 14px; display: grid; place-items: center; background: #b71d25; color: #fff8f2; font-size: 24px; font-weight: 1000; }}
.name {{ min-width: 0; font-size: 28px; font-weight: 1000; color: #2d2924; }}
.school {{ margin-top: 5px; font-size: 16px; font-weight: 800; color: #7a7066; }}
.priority {{ display: inline-flex; align-items: center; justify-content: center; min-height: 40px; border-radius: 999px; padding: 0 16px; background: #f4e5db; color: #8a2a1d; font-size: 17px; font-weight: 1000; }}
.reasons {{ min-width: 0; display: grid; gap: 7px; }}
.reason {{ font-size: 18px; line-height: 1.32; font-weight: 800; color: #514941; }}
.empty {{ min-height: 360px; display: grid; place-items: center; border: 1px solid #e7ded2; border-radius: 18px; background: #fffbf3; font-size: 26px; font-weight: 900; color: #5d554d; }}
</style>
</head>
<body>
  <main class="sheet">
    <section class="top">
      <div>
        <div class="eyebrow">상담 우선 후보</div>
        <h1>{len(candidates)}명 목록</h1>
        <div class="meta">기준일 {today} · 최근 {period_days}일 출결/기록 신호</div>
      </div>
      {logo}
    </section>
    <section class="list">{rows}</section>
    {empty}
  </main>
</body>
</html>"""


def consultation_candidates_image_height(payload: dict[str, Any]) -> int:
    count = len([item for item in payload.get("candidates") or [] if isinstance(item, dict)])
    return 300 + max(1, min(count, 10)) * 112


def _candidate_row(index: int, item: dict[str, Any]) -> str:
    student = item.get("student") if isinstance(item.get("student"), dict) else item
    name = escape(str(student.get("name") or item.get("name") or "이름 없음"))
    profile = escape(_profile_text(student))
    priority = escape(_priority_label(item.get("priority")) or "확인")
    reasons = [str(reason).strip() for reason in item.get("reasons") or [] if str(reason).strip()]
    reasons_html = "".join(f"<div class='reason'>{escape(reason)}</div>" for reason in reasons[:3])
    if not reasons_html:
        reasons_html = "<div class='reason'>상담 사유 데이터 없음</div>"
    return (
        "<article class='row'>"
        f"<div class='rank'>{index}</div>"
        f"<div><div class='name'>{name}</div><div class='school'>{profile}</div></div>"
        f"<div class='priority'>우선순위 {priority}</div>"
        f"<div class='reasons'>{reasons_html}</div>"
        "</article>"
    )


def _profile_text(student: dict[str, Any]) -> str:
    parts = [str(student.get(key) or "").strip() for key in ("school", "grade")]
    return " · ".join(part for part in parts if part) or "프로필 확인 필요"


def _logo_html(path: Path | None) -> str:
    if path and path.exists():
        return f"<img class='logo' src='{path.as_uri()}' alt='MAX 체대입시'>"
    return "<div class='logo-text'>MAX</div>"
