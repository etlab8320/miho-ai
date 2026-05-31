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
from .report_fonts import PRETENDARD_FAMILY, report_font_css

# Korean-first font stack. The bundled Pretendard webfont (embedded as base64
# @font-face by report_font_css) is the primary face so the report renders in a
# clean Korean typeface offline; the remaining names are robust system fallbacks.
_FONT_STACK = (
    f"'{PRETENDARD_FAMILY}','Goyang','GoyangDeogyang','Pretendard',"
    "'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif"
)

# Design tokens (light, clean — KBO/health-report card feel).
_CSS = f"""
:root{{
  --bg:#eef0f4;--card:#ffffff;--ink:#16181d;--ink-soft:#3a4150;--muted:#717784;
  --line:#e6e9ef;--line-soft:#f0f2f6;--row-alt:#f8fafc;
  --male:#2f6df6;--male-soft:#eaf1ff;--female:#e8588f;--female-soft:#fdeef4;
  --neutral:#5b6472;--neutral-soft:#eef0f4;
  --best:#0a8f6a;--best-soft:#e4f6ef;--avg-bg:#f3f5f9;
  --accent:#111827;
}}
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{background:var(--bg);}}
body{{font-family:{_FONT_STACK};
  color:var(--ink);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  padding:52px 48px;}}
.sheet{{width:1180px;margin:0 auto;background:var(--card);border-radius:24px;
  padding:0 0 30px;overflow:hidden;
  box-shadow:0 1px 2px rgba(20,24,29,.05),0 28px 64px -28px rgba(20,24,29,.28);
  border:1px solid #eceef3;}}
/* ---- header band: title + brand, with a thin accent rule underneath ---- */
.top{{display:flex;justify-content:space-between;align-items:flex-start;
  padding:40px 46px 26px;border-bottom:1px solid var(--line);
  background:linear-gradient(180deg,#fbfcfe,#ffffff);}}
.headline{{min-width:0;}}
.title{{font-size:33px;font-weight:700;letter-spacing:-.025em;line-height:1.12;}}
.title::after{{content:"";display:block;width:46px;height:4px;border-radius:999px;
  background:var(--accent);margin-top:14px;}}
.subtitle{{margin-top:14px;font-size:15px;color:var(--muted);font-weight:500;letter-spacing:-.01em;}}
.brandtag{{display:flex;flex-direction:column;align-items:flex-end;gap:9px;flex:none;}}
.brandtag .stamp{{height:52px;width:auto;opacity:.96;}}
.brandtag .txt{{text-align:right;font-size:11.5px;color:#aab0bd;font-weight:600;line-height:1.5;}}
.brandtag .txt b{{color:var(--ink);font-weight:700;display:block;font-size:14px;letter-spacing:-.01em;}}
.body{{padding:8px 46px 0;}}
/* ---- section label: a coloured pill anchor + group name + count ---- */
.seclabel{{display:flex;align-items:center;gap:11px;margin:28px 0 13px;
  font-size:17px;font-weight:700;letter-spacing:-.01em;}}
.seclabel .tag{{display:inline-flex;align-items:center;justify-content:center;
  min-width:30px;height:26px;padding:0 9px;border-radius:8px;
  font-size:12.5px;font-weight:700;color:#fff;background:var(--neutral);
  letter-spacing:.02em;}}
.seclabel.male .tag{{background:var(--male);}}
.seclabel.female .tag{{background:var(--female);}}
.seclabel .n{{color:var(--muted);font-weight:600;font-size:13.5px;}}
/* ---- table: header(th) and value(td) share center align + fixed colgroup
   width so header and number always line up on the column centre. ---- */
table{{width:100%;border-collapse:collapse;table-layout:fixed;}}
th,td{{padding:14px 16px;font-size:15px;font-variant-numeric:tabular-nums;text-align:center;}}
thead th{{font-size:12.5px;font-weight:700;color:var(--muted);letter-spacing:.01em;
  border-bottom:1.5px solid var(--line);padding:8px 16px 11px;white-space:nowrap;}}
thead th .unit{{display:block;font-size:10.5px;color:#aab0bd;font-weight:600;margin-top:3px;}}
th.no,td.no{{text-align:center;}}
th.name,td.name{{text-align:left;}}
td.name{{font-weight:700;color:var(--ink);letter-spacing:-.01em;}}
th.meta,td.meta{{text-align:left;color:var(--muted);font-size:13.5px;font-weight:500;}}
tbody td{{border-bottom:1px solid var(--line-soft);}}
tbody tr:nth-child(even) td{{background:var(--row-alt);}}
tbody tr:last-child td{{border-bottom:none;}}
td .best{{display:inline-block;padding:3px 10px;border-radius:8px;
  background:var(--best-soft);color:var(--best);font-weight:700;}}
td .none{{color:#cfd4dd;}}
.rank{{display:inline-flex;width:27px;height:27px;border-radius:9px;
  background:var(--neutral-soft);color:var(--neutral);font-size:13px;font-weight:700;
  align-items:center;justify-content:center;}}
.seclabel.male ~ table .rank,.male-rank{{background:var(--male-soft);color:var(--male);}}
tr.avg td{{background:var(--avg-bg);border-top:1.5px solid var(--line);
  border-bottom:none;font-weight:700;}}
tr.avg td.name{{color:var(--ink-soft);}}
tr.avg.male td.name{{color:var(--male);}}
tr.avg.female td.name{{color:var(--female);}}
/* ---- roster (no data columns): name directory in a 2-up grid ---- */
.roster{{display:grid;grid-template-columns:1fr 1fr;gap:10px 18px;margin:4px 0 6px;}}
.roster .person{{display:flex;align-items:center;gap:14px;padding:13px 16px;
  border:1px solid var(--line);border-radius:14px;background:#fcfdff;min-width:0;}}
.roster .num{{display:inline-flex;flex:none;width:30px;height:30px;border-radius:9px;
  background:var(--neutral-soft);color:var(--neutral);font-size:13.5px;font-weight:700;
  align-items:center;justify-content:center;}}
.roster.male .num{{background:var(--male-soft);color:var(--male);}}
.roster.female .num{{background:var(--female-soft);color:var(--female);}}
.roster .who{{min-width:0;}}
.roster .pname{{font-size:16px;font-weight:700;color:var(--ink);letter-spacing:-.01em;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.roster .pmeta{{margin-top:3px;font-size:13px;color:var(--muted);font-weight:500;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.foot{{display:flex;justify-content:space-between;align-items:center;
  margin:26px 46px 0;padding-top:16px;border-top:1px solid var(--line);}}
.foot .note{{font-size:13px;color:var(--muted);font-weight:500;}}
.foot .src{{font-size:12px;color:#b4bac5;font-weight:600;letter-spacing:.01em;}}
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
    cols = ['<col style="width:64px">', '<col style="width:104px">', '<col style="width:132px">']
    cols += ["<col>" for _ in columns]
    return "<colgroup>" + "".join(cols) + "</colgroup>"


def _thead(columns: list[ColumnSpec]) -> str:
    ths = ['<th class="no">No</th>', '<th class="name">이름</th>', '<th class="meta">구분</th>']
    for col in columns:
        unit = f'<span class="unit">{html.escape(col.unit)}</span>' if col.unit else ""
        ths.append(f"<th>{html.escape(col.label)}{unit}</th>")
    return "<thead><tr>" + "".join(ths) + "</tr></thead>"


def _rank_class(group: GroupSpec) -> str:
    return " male-rank" if group.kind == "male" else ""


def _render_roster(group: GroupSpec) -> str:
    """No data columns: render the rows as a clean numbered name directory."""
    kind = f" {html.escape(group.kind)}" if group.kind else ""
    cards: list[str] = []
    for idx, row in enumerate(group.rows, start=1):
        name = html.escape(str(row.get("name") or ""))
        meta = str(row.get("meta") or "")
        meta_el = f'<div class="pmeta">{html.escape(meta)}</div>' if meta else ""
        cards.append(
            f'<div class="person"><span class="num">{idx}</span>'
            f'<div class="who"><div class="pname">{name}</div>{meta_el}</div></div>'
        )
    return f'<div class="roster{kind}">' + "".join(cards) + "</div>"


def _render_group(spec: ReportSpec, group: GroupSpec) -> str:
    if not spec.columns:
        return _render_roster(group)

    rows = _sorted_rows(group, spec.rank_by)
    best = _best_keys(rows, spec.columns) if spec.highlight_best else {}
    rank_cls = _rank_class(group)
    body: list[str] = []
    for idx, row in enumerate(rows, start=1):
        rank = f'<span class="rank{rank_cls}">{idx}</span>'
        cells = [
            f'<td class="no">{rank}</td>',
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


def _section_label(spec: ReportSpec, group: GroupSpec) -> str:
    if not group.label:
        return ""
    kind = f" {html.escape(group.kind)}" if group.kind else ""
    tag = html.escape(group.kind[:1].upper()) if group.kind else "•"
    # With data columns, show how many of the listed people actually have records;
    # for a plain roster (no columns) that distinction is meaningless, so omit it.
    if spec.columns:
        n = sum(
            1 for r in group.rows
            if any(_as_number(r.get(c.key)) is not None for c in spec.columns)
        )
        count = f'· {len(group.rows)}명 (기록 {n}명)'
    else:
        count = f'· {len(group.rows)}명'
    return (
        f'<div class="seclabel{kind}"><span class="tag">{tag or "•"}</span>'
        f'{html.escape(group.label)} <span class="n">{count}</span></div>'
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
            sections.append(_section_label(spec, group))
        sections.append(_render_group(spec, group))

    note = f'<div class="note">{html.escape(spec.note)}</div>' if spec.note else "<div class='note'></div>"
    foot = f'<div class="foot">{note}<div class="src">{html.escape(spec.source)}</div></div>'

    subtitle = f'<div class="subtitle">{html.escape(spec.subtitle)}</div>' if spec.subtitle else ""
    return (
        "<!DOCTYPE html><html lang='ko'><head><meta charset='UTF-8'>"
        f"<style>{report_font_css()}{_CSS}</style></head><body><div class='sheet'>"
        f"<div class='top'><div class='headline'><div class='title'>{html.escape(spec.title)}</div>{subtitle}</div>{brand}</div>"
        f"<div class='body'>" + "".join(sections) + "</div>"
        + foot
        + "</div></body></html>"
    )
