"""Reusable table-report design system for academy image reports.

"정확성은 코드, 판단은 LLM": the caller (LLM) decides *what* columns/groups/rows
to show; this module renders them *exactly* per the contract — values are placed
strictly by column order, so a header and its values can never drift out of
alignment. Group averages and per-column bests are computed here in code, never
by the model. Contains NO domain literals (school/student/event names) — every
value is runtime data.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any

from .brand_assets import academy_brand_logo_src

# Design tokens (light, trendy). Mirrors the approved mockup.
_CSS = """
:root{
  --bg:#f4f5f7;--card:#fff;--ink:#16181d;--muted:#6b7180;--line:#e9ebef;
  --line-soft:#f1f2f5;--row-alt:#fafbfc;--male:#2f6df6;--female:#e8588f;
  --best:#0f9d76;--avg-bg:#f5f6f8;
}
*{box-sizing:border-box;margin:0;padding:0;}
html,body{background:var(--bg);}
body{font-family:"Pretendard","Apple SD Gothic Neo","Helvetica Neue",-apple-system,sans-serif;
  color:var(--ink);-webkit-font-smoothing:antialiased;padding:48px;}
.sheet{width:1180px;margin:0 auto;background:var(--card);border-radius:22px;padding:44px 46px 34px;
  box-shadow:0 1px 2px rgba(20,24,29,.04),0 20px 50px -24px rgba(20,24,29,.18);}
.top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:26px;}
.title{font-size:30px;font-weight:800;letter-spacing:-.02em;}
.subtitle{margin-top:8px;font-size:14.5px;color:var(--muted);font-weight:500;}
.brandtag{display:flex;flex-direction:column;align-items:flex-end;gap:8px;}
.brandtag .stamp{height:56px;width:auto;opacity:.95;}
.brandtag .txt{text-align:right;font-size:12px;color:#aab0bd;font-weight:600;line-height:1.5;}
.brandtag .txt b{color:var(--ink);font-weight:800;display:block;font-size:14px;}
.seclabel{display:flex;align-items:center;gap:9px;margin:24px 0 10px;font-size:15px;font-weight:800;}
.seclabel .tag{font-size:11.5px;font-weight:700;color:#fff;padding:3px 9px;border-radius:7px;background:var(--muted);}
.seclabel.male .tag{background:var(--male);}
.seclabel.female .tag{background:var(--female);}
.seclabel .n{color:var(--muted);font-weight:600;font-size:13px;}
table{width:100%;border-collapse:collapse;table-layout:fixed;}
/* header(th) and value(td) share the SAME center alignment + fixed colgroup
   width, so header and number line up on the column centre. */
th,td{padding:13px 16px;font-size:14.5px;font-variant-numeric:tabular-nums;text-align:center;}
thead th{font-size:12.5px;font-weight:700;color:var(--muted);
  border-bottom:1.5px solid var(--line);padding-bottom:11px;white-space:nowrap;}
thead th .unit{display:block;font-size:10.5px;color:#aab0bd;font-weight:600;margin-top:2px;}
th.name,td.name{text-align:left;}
td.name{font-weight:700;}
th.meta,td.meta{text-align:left;color:var(--muted);font-size:13px;font-weight:500;}
tbody td{border-bottom:1px solid var(--line-soft);}
tbody tr:nth-child(even) td{background:var(--row-alt);}
td .best{color:var(--best);font-weight:800;}
td .none{color:#c4c9d2;}
.rank{display:inline-flex;width:22px;height:22px;border-radius:7px;background:#f0f1f4;
  color:var(--muted);font-size:12px;font-weight:700;align-items:center;justify-content:center;}
tr.avg td{background:var(--avg-bg);border-bottom:none;font-weight:800;}
tr.avg.male td.name{color:var(--male);}
tr.avg.female td.name{color:var(--female);}
.foot{display:flex;justify-content:space-between;align-items:center;margin-top:24px;
  padding-top:15px;border-top:1px solid var(--line);}
.foot .note{font-size:12.5px;color:var(--muted);font-weight:500;}
.foot .src{font-size:12px;color:#b4bac5;font-weight:600;}
"""


@dataclass
class ColumnSpec:
    key: str
    label: str
    unit: str = ""
    best: str = "high"   # "high" (큰 값이 우수) | "low" (작은 값이 우수, 예: 시간) | "none"


@dataclass
class GroupSpec:
    label: str
    rows: list[dict[str, Any]]
    kind: str = ""          # "male" | "female" | "" (styling/label only)
    avg_label: str = ""     # e.g. "남자 평균"; empty → no average row


@dataclass
class ReportSpec:
    title: str
    subtitle: str = ""
    columns: list[ColumnSpec] = field(default_factory=list)
    groups: list[GroupSpec] = field(default_factory=list)
    highlight_best: bool = True
    show_group_avg: bool = True
    rank_by: str = ""       # column key to sort each group by (desc); "" → keep order
    note: str = ""
    source: str = "Miho AI · PACA/Peak"


def _as_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Any) -> str:
    """Display a value; numbers keep their given precision, blanks become '–'."""
    if value is None or value == "":
        return '<span class="none">–</span>'
    return html.escape(str(value))


def _column_average(rows: list[dict[str, Any]], key: str) -> float | None:
    nums = [n for n in (_as_number(r.get(key)) for r in rows) if n is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _fmt_avg(value: float | None) -> str:
    if value is None:
        return '<span class="none">–</span>'
    # 1 decimal place, but drop trailing .0 for whole numbers
    rounded = round(value, 1)
    return html.escape(f"{rounded:g}")


def _best_keys(rows: list[dict[str, Any]], columns: list[ColumnSpec]) -> dict[str, float]:
    """Per-column best value within a group, per the column's direction.

    Direction (high/low/none) is decided by the caller (LLM) — the code never
    hardcodes which event is "lower is better"; it just honours the flag.
    """
    best: dict[str, float] = {}
    for col in columns:
        if col.best == "none":
            continue
        nums = [n for n in (_as_number(r.get(col.key)) for r in rows) if n is not None]
        if nums:
            best[col.key] = min(nums) if col.best == "low" else max(nums)
    return best


def _sorted_rows(group: GroupSpec, rank_by: str) -> list[dict[str, Any]]:
    if not rank_by:
        return list(group.rows)
    def sort_key(row: dict[str, Any]) -> float:
        n = _as_number(row.get(rank_by))
        return n if n is not None else float("-inf")
    return sorted(group.rows, key=sort_key, reverse=True)


def _colgroup(columns: list[ColumnSpec]) -> str:
    cols = ['<col style="width:46px">', '<col style="width:96px">', '<col style="width:120px">']
    cols += ["<col>" for _ in columns]
    return "<colgroup>" + "".join(cols) + "</colgroup>"


def _thead(columns: list[ColumnSpec]) -> str:
    ths = ['<th class="meta">No</th>', '<th class="name">이름</th>', '<th class="meta">구분</th>']
    for col in columns:
        unit = f'<span class="unit">{html.escape(col.unit)}</span>' if col.unit else ""
        ths.append(f"<th>{html.escape(col.label)}{unit}</th>")
    return "<thead><tr>" + "".join(ths) + "</tr></thead>"


def _render_group(spec: ReportSpec, group: GroupSpec) -> str:
    rows = _sorted_rows(group, spec.rank_by)
    best = _best_keys(rows, spec.columns) if spec.highlight_best else {}
    body: list[str] = []
    for idx, row in enumerate(rows, start=1):
        has_any = any(_as_number(row.get(c.key)) is not None for c in spec.columns)
        rank = f'<span class="rank">{idx}</span>' if has_any else '<span class="rank">–</span>'
        cells = [
            f'<td class="meta">{rank}</td>',
            f'<td class="name">{html.escape(str(row.get("name") or ""))}</td>',
            f'<td class="meta">{html.escape(str(row.get("meta") or ""))}</td>',
        ]
        for col in spec.columns:
            raw = row.get(col.key)
            num = _as_number(raw)
            is_best = spec.highlight_best and num is not None and num == best.get(col.key)
            inner = _fmt(raw)
            if is_best:
                inner = f'<span class="best">{inner}</span>'
            cells.append(f"<td>{inner}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")

    if spec.show_group_avg and group.avg_label:
        valid = sum(1 for r in rows if any(_as_number(r.get(c.key)) is not None for c in spec.columns))
        avg_cells = [
            "<td></td>",
            f'<td class="name">{html.escape(group.avg_label)}</td>',
            f'<td class="meta">{valid}명</td>',
        ]
        for col in spec.columns:
            avg_cells.append(f"<td>{_fmt_avg(_column_average(rows, col.key))}</td>")
        kind = f" {html.escape(group.kind)}" if group.kind else ""
        body.append(f'<tr class="avg{kind}">' + "".join(avg_cells) + "</tr>")

    table = (
        f"<table>{_colgroup(spec.columns)}{_thead(spec.columns)}<tbody>"
        + "".join(body)
        + "</tbody></table>"
    )
    return table


def _section_label(group: GroupSpec) -> str:
    if not group.label:
        return ""
    kind = f" {html.escape(group.kind)}" if group.kind else ""
    tag = html.escape(group.kind[:1].upper()) if group.kind else "•"
    n = sum(1 for r in group.rows if any(str(v).strip() for k, v in r.items() if k not in ("name", "meta")))
    return (
        f'<div class="seclabel{kind}"><span class="tag">{tag or "•"}</span>'
        f'{html.escape(group.label)} <span class="n">· {len(group.rows)}명 (기록 {n}명)</span></div>'
    )


def render_report_html(spec: ReportSpec) -> str:
    """Render a ReportSpec to a full standalone HTML document."""
    logo = academy_brand_logo_src()
    stamp = f'<img class="stamp" src="{logo}" alt="stamp">' if logo else ""
    brand = (
        f'<div class="brandtag">{stamp}'
        f'<div class="txt"><b>Miho AI</b>PACA / Peak</div></div>'
    )

    sections: list[str] = []
    multi = len(spec.groups) > 1
    for group in spec.groups:
        if multi or group.label:
            sections.append(_section_label(group))
        sections.append(_render_group(spec, group))

    note = f'<div class="note">{html.escape(spec.note)}</div>' if spec.note else "<div class='note'></div>"
    foot = f'<div class="foot">{note}<div class="src">{html.escape(spec.source)}</div></div>'

    subtitle = f'<div class="subtitle">{html.escape(spec.subtitle)}</div>' if spec.subtitle else ""
    return (
        "<!DOCTYPE html><html lang='ko'><head><meta charset='UTF-8'>"
        f"<style>{_CSS}</style></head><body><div class='sheet'>"
        f"<div class='top'><div><div class='title'>{html.escape(spec.title)}</div>{subtitle}</div>{brand}</div>"
        + "".join(sections)
        + foot
        + "</div></body></html>"
    )
