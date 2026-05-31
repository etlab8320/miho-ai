"""T-ID tests for the reusable report design system.

Verifies the contract that makes "header-value alignment" structurally
guaranteed: values are placed strictly by column order, group averages and
per-column bests are computed in code, and no domain literals are baked in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import plugins.academy_ops.report_design as rd
from plugins.academy_ops.report_design import (
    ColumnSpec,
    GroupSpec,
    ReportSpec,
    _column_average,
    render_report_html,
)

COLS = [
    ColumnSpec("jump", "제자리멀리뛰기", "cm"),
    ColumnSpec("run", "20m", "초"),
    ColumnSpec("back", "배근력", "kg"),
]


@pytest.fixture(autouse=True)
def _no_logo(monkeypatch):
    # The real stamp.png base64 is large and can contain substrings like "low"
    # that break index-based assertions. Default to no logo; T6 overrides.
    monkeypatch.setattr(rd, "academy_brand_logo_src", lambda: None)


def _body(html: str) -> str:
    # Position assertions are about rendered table content, not the <style>
    # block (whose CSS keywords like "overflow" contain "low"). Scope to body.
    _, _, rest = html.partition("</style>")
    return rest or html


def _spec(rows, **kw):
    return ReportSpec(
        title="테스트 보고서",
        columns=COLS,
        groups=[GroupSpec(label="A조", rows=rows, kind="male", avg_label="평균")],
        **kw,
    )


def test_t1_values_follow_column_order():
    rows = [{"name": "가", "meta": "고3", "jump": 295, "run": 13.7, "back": 165}]
    html = _body(render_report_html(_spec(rows, highlight_best=False)))
    # Each value appears in the same order as its column → header/value aligned.
    assert html.index("295") < html.index("13.7") < html.index("165")


def test_t2_missing_value_becomes_dash_without_shifting():
    rows = [{"name": "가", "meta": "고3", "jump": 295}]  # run, back missing
    html = render_report_html(_spec(rows, highlight_best=False))
    assert "–" in html
    # 3 meta/name/meta cells + 3 column cells = 6 <td> in the data row region
    assert html.count("<td") >= 6


def test_t3_group_average_computed_in_code():
    rows = [{"jump": 200, "name": "가"}, {"jump": 300, "name": "나"}]
    assert _column_average(rows, "jump") == 250.0
    # blanks excluded
    rows2 = [{"jump": 200}, {"jump": None}, {"jump": ""}]
    assert _column_average(rows2, "jump") == 200.0
    assert _column_average([{"jump": None}], "jump") is None


def test_t4_highlights_only_the_best_per_column():
    rows = [{"name": "가", "jump": 200}, {"name": "나", "jump": 300}]
    html = render_report_html(_spec(rows, rank_by=""))
    assert '<span class="best">300' in html
    assert '<span class="best">200' not in html


def test_t4b_low_direction_highlights_minimum():
    cols = [ColumnSpec("time", "20m왕복", "초", best="low")]
    rows = [{"name": "가", "time": 15.0}, {"name": "나", "time": 13.0}]
    spec = ReportSpec(
        title="T", columns=cols,
        groups=[GroupSpec(label="A", rows=rows, avg_label="평균")],
    )
    html = render_report_html(spec)
    assert '<span class="best">13' in html      # 낮을수록 좋은 종목 → 최소값 강조
    assert '<span class="best">15' not in html


def test_t4c_none_direction_highlights_nothing():
    cols = [ColumnSpec("x", "비강조", "", best="none")]
    rows = [{"name": "가", "x": 1}, {"name": "나", "x": 9}]
    spec = ReportSpec(title="T", columns=cols, groups=[GroupSpec(label="A", rows=rows)])
    html = render_report_html(spec)
    assert 'class="best"' not in html


def test_t5_rank_by_sorts_descending():
    rows = [{"name": "low", "jump": 100}, {"name": "high", "jump": 999}]
    html = _body(render_report_html(_spec(rows, rank_by="jump")))
    assert html.index("high") < html.index("low")


def test_t6_stamp_injected_when_logo_available(monkeypatch):
    monkeypatch.setattr(rd, "academy_brand_logo_src", lambda: "data:image/png;base64,ZZZ")
    html = render_report_html(_spec([{"name": "가", "jump": 1}]))
    assert "data:image/png;base64,ZZZ" in html
    assert "stamp" in html


def test_t7_no_hardcoded_domain_literals():
    src = Path("plugins/academy_ops/report_design.py").read_text(encoding="utf-8")
    # 특정 학교/학생/종목명이 코드에 박히면 안 된다 (전부 런타임 데이터)
    for bad in ["문산", "제일고", "여민석", "오철민", "제멀", "제자리멀리뛰기", "메디신볼"]:
        assert bad not in src, f"domain literal leaked into design module: {bad}"


def test_t8_empty_groups_renders_without_error():
    spec = ReportSpec(title="빈 보고서", columns=COLS, groups=[])
    html = render_report_html(spec)
    assert "빈 보고서" in html


def test_group_average_excludes_dash_count():
    # avg_label row should report the count of rows that actually have data
    rows = [{"name": "가", "jump": 10}, {"name": "나"}]  # 나 has no data
    html = render_report_html(_spec(rows))
    assert "평균" in html
    assert "1명" in html  # only 가 counted
