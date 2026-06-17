from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

REGIONAL_MINIMUM_CSAT = (
    "4개 영역(국어, 수학, 영어, 탐구) 중 3개 영역 등급 합이 7등급 이내 "
    "(탐구영역의 등급은 2개 과목 등급 평균을 반영함)"
)

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


@_skip_no_db
def test_calculate_score_snu_student_comprehensive_tracks_are_noncalc_with_official_minimums() -> None:
    subjects = [{"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"}]

    opportunity = calculate_score("230", subjects, {}, {})
    assert opportunity["status"] == "non_calculation_track"
    assert opportunity["strategy"] == "official_formula_plugin"
    assert opportunity["formula_key"] == "SNU_2027_STUDENT_RECORD_COMPREHENSIVE_QUALITATIVE_NOT_NUMERIC"
    assert opportunity["minimum_csat"] == {
        "has_minimum": False,
        "detail": "수능 최저학력기준 미적용",
    }

    regional = calculate_score("231", subjects, {}, {})
    assert regional["status"] == "non_calculation_track"
    assert regional["strategy"] == "official_formula_plugin"
    assert regional["formula_key"] == "SNU_2027_STUDENT_RECORD_COMPREHENSIVE_QUALITATIVE_NOT_NUMERIC"
    assert regional["minimum_csat"] == {
        "has_minimum": True,
        "detail": REGIONAL_MINIMUM_CSAT,
    }
