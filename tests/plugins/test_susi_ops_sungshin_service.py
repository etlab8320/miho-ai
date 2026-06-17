from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1", "과목구분": "일반"},
    ]


@_skip_no_db
def test_calculate_score_sungshin_not_in_official_guide_is_non_calculation() -> None:
    result = calculate_score("264", _subjects(), {"unexcused_absence_days": 7}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "non_calculation_rule"
    assert result["confidence"] == "official_pdf_codex_verified_not_in_guide"
    assert result["semester_weights"]["N학년"] == "not_applicable"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "2027 공식 모집단위 미존재 행"}
