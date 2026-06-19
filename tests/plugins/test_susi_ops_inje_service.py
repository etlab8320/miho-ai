from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "INJE_2027_OFFICIAL_10_SUBJECT_RECORD_COMPONENTS"


def _subjects(rank_grade: str = "1") -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 3, "등급": rank_grade, "과목구분": "일반"},
        {"학년": 1, "학기": 2, "교과": "국어", "과목": "국어2", "이수단위": 3, "등급": rank_grade, "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "수학", "과목": "수학1", "이수단위": 3, "등급": rank_grade, "과목구분": "일반"},
        {"학년": 2, "학기": 2, "교과": "수학", "과목": "수학2", "이수단위": 3, "등급": rank_grade, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 3, "등급": rank_grade, "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "영어2", "이수단위": 3, "등급": rank_grade, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회", "이수단위": 3, "등급": rank_grade, "과목구분": "일반"},
        {"학년": 1, "학기": 2, "교과": "과학", "과목": "과학", "이수단위": 3, "등급": rank_grade, "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": rank_grade, "과목구분": "일반"},
        {"학년": 3, "학기": 1, "교과": "기술가정", "과목": "정보", "이수단위": 3, "등급": rank_grade, "과목구분": "일반"},
    ]


def _short_subjects(rank_grade: str = "2") -> list[dict[str, object]]:
    return _subjects(rank_grade)[:-1]


@_skip_no_db
def test_calculate_score_inje_practical_track_exposes_official_contract() -> None:
    result = calculate_score("310", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["used_subjects"] == 10
    assert result["student_record_score"] == pytest.approx(30.0)
    assert result["record_full_score"] == pytest.approx(30.0)
    assert result["practical_full_score"] == pytest.approx(70.0)
    assert result["full_practical_total"] == pytest.approx(100.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_inje_short_subjects_use_average_grade_formula() -> None:
    need_based = calculate_score("319", _short_subjects(), {}, {})
    specialized = calculate_score("321", _short_subjects(), {}, {})

    assert need_based["status"] == "calculated"
    assert need_based["used_subjects"] == 9
    assert need_based["average_grade"] == pytest.approx(2.0)
    assert need_based["student_record_score"] == pytest.approx(93.5)
    assert need_based["full_practical_total"] == pytest.approx(93.5)
    assert specialized["student_record_score"] == pytest.approx(74.8)
    assert specialized["full_practical_total"] == pytest.approx(94.8)


@_skip_no_db
def test_calculate_score_inje_record_only_tracks_are_out_of_100() -> None:
    need_based = calculate_score("319", _subjects(), {}, {})
    rural = calculate_score("320", _subjects(), {}, {})

    assert need_based["status"] == "calculated"
    assert need_based["used_subjects"] == 10
    assert need_based["student_record_score"] == pytest.approx(100.0)
    assert need_based["full_practical_total"] == pytest.approx(100.0)
    assert rural["student_record_score"] == pytest.approx(100.0)
    assert rural["full_practical_total"] == pytest.approx(100.0)


@_skip_no_db
def test_calculate_score_inje_specialized_track_includes_interview20() -> None:
    result = calculate_score("321", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == FORMULA_KEY
    assert result["used_subjects"] == 10
    assert result["student_record_score"] == pytest.approx(80.0)
    assert result["practical_full_score"] == pytest.approx(20.0)
    assert result["full_practical_total"] == pytest.approx(100.0)


@_skip_no_db
def test_calculate_score_inje_absences_are_ineligible() -> None:
    practical_absent = calculate_score("310", _subjects(), {"practical_event_absent": True}, {})
    practical_interview_absent = calculate_score("310", _subjects(), {"interview_absent": True}, {})
    specialized_interview_absent = calculate_score("321", _subjects(), {"interview_absent": True}, {})

    assert practical_absent["status"] == "practical_absent_ineligible"
    assert practical_interview_absent["status"] == "interview_absent_ineligible"
    assert specialized_interview_absent["status"] == "interview_absent_ineligible"
