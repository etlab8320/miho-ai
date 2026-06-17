from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 4, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 4, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 4, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "통합사회", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "과학", "과목": "통합과학", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "과학", "과목": "진로과학", "이수단위": 3, "성취도": "A", "과목구분": "진로"},
    ]


@_skip_no_db
def test_calculate_score_seoul_womens_sports_course_practical() -> None:
    result = calculate_score("227", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SWU_2027_SPORTS_RECORD60_PRACTICAL40"
    assert result["student_record_score"] == pytest.approx(60.0)
    assert result["record_full_score"] == pytest.approx(60.0)
    assert result["practical_full_score"] == pytest.approx(40.0)
    assert result["full_practical_total"] == pytest.approx(100.0)
    assert result["used_subjects"] == 5
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_seoul_womens_barom_interview_is_noncalc() -> None:
    result = calculate_score("234", _subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SWU_2027_NON_CALCULATION_TRACK"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
