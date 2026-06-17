from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _perfect_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 2, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 2, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회1", "이수단위": 2, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 2, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 2, "성취도": "A"},
    ]


@_skip_no_db
def test_calculate_score_dankook_practical_excellence_uses_official_formula() -> None:
    result = calculate_score("115", _perfect_subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "DANKOOK_2027_OFFICIAL_COURSE_ATTENDANCE_PRACTICAL"
    assert result["student_record_score"] == pytest.approx(200.0)
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(800.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"]["has_minimum"] is False
