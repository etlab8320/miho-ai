"""Cover template rendering checks for academy PDF packages."""

from __future__ import annotations

import re

from plugins.academy_ops.hakjong_report_tool import _render_html as render_hakjong
from plugins.academy_ops.practical_reco_tool import _render_html as render_practical
from tests.plugins.test_academy_hakjong_report_tool import _base_content as hakjong_content
from tests.plugins.test_academy_practical_reco import _base_content as practical_content


def test_practical_cover_uses_premium_sheet_layout() -> None:
    html = render_practical(practical_content())

    assert 'class="coverSheet"' in html
    assert "계산 기준" in html
    assert "내신환산" in html
    assert "전년도 컷" in html
    assert "실기종목" in html
    assert "실기종목·수능최저" in html
    assert 'class="identityCard"' not in html
    assert 'class="metricsRow"' not in html


def test_hakjong_cover_uses_aligned_dossier_layout() -> None:
    html = render_hakjong(hakjong_content())

    assert 'class="coverSheet"' in html
    assert 'class="coverBadge"' in html
    assert "전형 구조" in html
    assert "학생부 근거" in html
    assert "평가축 분석" in html
    assert "면접·보완점" in html
    assert 'class="stamp"' not in html
    assert 'class="metricsRow"' not in html


def test_hakjong_gauge_supports_semantic_tone_aliases() -> None:
    content = hakjong_content()
    tones = ["danger", "warn", "medium"]
    for gauge, tone in zip(content["diagnosis_section"]["gauges"], tones):
        gauge["tone"] = tone

    html = render_hakjong(content)

    assert ".fill.danger" in html
    assert ".fill.warn" in html
    assert ".fill.medium" in html
    for tone in tones:
        assert f'class="fill {tone}"' in html


def test_hakjong_strategy_actions_render_as_single_reading_column() -> None:
    html = render_hakjong(hakjong_content())

    action_rule = re.search(r"\.actionGrid\s*\{[^}]+\}", html)
    assert action_rule is not None
    assert "grid-template-columns: 1fr;" in action_rule.group(0)
    assert "grid-template-columns: 1fr 1fr" not in action_rule.group(0)
