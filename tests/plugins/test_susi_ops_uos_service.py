from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


@_skip_no_db
def test_calculate_score_uos_student_comprehensive_is_noncalc() -> None:
    subjects = [{"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"}]

    result = calculate_score("233", subjects, {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "UOS_2027_STUDENT_COMPREHENSIVE_INTERVIEW_NON_CALCULATION"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
