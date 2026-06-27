"""Consistency checks for the Miho AI operational scorecard."""

from __future__ import annotations

import re
from pathlib import Path


SCORECARD = Path("docs/miho-ai-100-point-scorecard.md")


def test_scorecard_table_matches_section_scores() -> None:
    text = SCORECARD.read_text(encoding="utf-8")
    table_scores = {
        name.strip(): int(score)
        for name, score in re.findall(r"^\| ([^|]+?) \| (\d+) \| 100 \|$", text, re.MULTILINE)
    }
    section_scores = {
        _section_table_name(name): int(score)
        for name, score in re.findall(
            r"^## \d+\. (.+?)\n\n현재: (\d+)/100$", text, re.MULTILINE
        )
    }

    assert table_scores
    assert section_scores
    assert table_scores == section_scores


def test_scorecard_does_not_call_readiness_score_operational_completion() -> None:
    text = SCORECARD.read_text(encoding="utf-8")
    assert "현재 총평: local/live-safe 기준 100/100" not in text
    assert "사용자 운영 통합 기준" in text
    assert "readiness 100은 필요조건" in text


def _section_table_name(section_name: str) -> str:
    if section_name == "도구 맵과 Tool Contract":
        return "도구 맵과 tool contract"
    if section_name == "Governance Reviewer 구조":
        return "Governance reviewer 구조"
    return section_name
