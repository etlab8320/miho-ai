from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

PRACTICAL_KEY = "JJU_2027_OFFICIAL_TOP3GROUP_CREDITWEIGHTED_TO_3_1_PRACTICAL30_70_CAREER_NA"
COURSE_KEY = "JJU_2027_OFFICIAL_TOP3GROUP_CREDITWEIGHTED_TO_3_1_COURSE100_CAREER_BONUS"


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 5, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 2, "교과": "국어", "과목": "국어2", "이수단위": 5, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 5, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 2, "교과": "영어", "과목": "영어2", "이수단위": 5, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학1", "이수단위": 5, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 2, "교과": "수학", "과목": "수학2", "이수단위": 5, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회1", "이수단위": 5, "등급": "9", "과목구분": "일반"},
        {"학년": 1, "학기": 2, "교과": "사회", "과목": "사회2", "이수단위": 5, "등급": "9", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "과학", "과목": "과학1", "이수단위": 5, "등급": "9", "과목구분": "일반"},
        {"학년": 1, "학기": 2, "교과": "과학", "과목": "과학2", "이수단위": 5, "등급": "9", "과목구분": "일반"},
    ]


def _subjects_with_career() -> list[dict[str, object]]:
    return _subjects() + [
        {"학년": 2, "학기": 1, "교과": "과학", "과목": "진로과학A", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        {"학년": 2, "학기": 2, "교과": "사회", "과목": "진로사회B", "이수단위": 2, "성취도": "B", "과목구분": "진로"},
    ]


def _subjects_with_cross_category_career() -> list[dict[str, object]]:
    return _subjects_with_career() + [
        {"학년": 2, "학기": 1, "교과": "체육", "과목": "스포츠생활", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        {"학년": 2, "학기": 2, "교과": "음악", "과목": "음악감상", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
    ]


@_skip_no_db
def test_calculate_score_jeonju_practical_track_uses_official_plugin() -> None:
    result = calculate_score("323", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == PRACTICAL_KEY
    assert result["used_subjects"] == 6
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["record_full_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_jeonju_practical_track_ignores_attendance_and_blocks_absence() -> None:
    attendance = {"unexcused_absence_days": 7, "unexcused_late": 1, "unexcused_early_leave": 3}
    calculated = calculate_score("323", _subjects(), attendance, {})
    absent = calculate_score("323", _subjects(), {"practical_absent": True}, {})

    assert calculated["student_record_score"] == pytest.approx(300.0)
    assert calculated["full_practical_total"] == pytest.approx(1000.0)
    assert absent["status"] == "practical_absent_ineligible"


@_skip_no_db
def test_calculate_score_jeonju_course_track_and_non_calculation() -> None:
    course = calculate_score("351", _subjects_with_career(), {}, {})
    non_calc = calculate_score("352", _subjects(), {}, {})

    assert course["status"] == "calculated"
    assert course["formula_key"] == COURSE_KEY
    assert course["used_subjects"] == 6
    assert course["student_record_score"] == pytest.approx(1005.0)
    assert course["full_practical_total"] == pytest.approx(1005.0)
    assert non_calc["status"] == "non_calculation_track"
    assert non_calc["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_jeonju_career_bonus_uses_all_career_subjects() -> None:
    result = calculate_score("351", _subjects_with_cross_category_career(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == COURSE_KEY
    assert result["student_record_score"] == pytest.approx(1006.0)
