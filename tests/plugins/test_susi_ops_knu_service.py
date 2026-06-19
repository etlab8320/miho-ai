from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _arts_pe_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "과학", "과목": "과학", "이수단위": 9, "등급": "9"},
        {"학년": 3, "학기": 2, "교과": "국어", "과목": "문학", "이수단위": 9, "등급": "9"},
    ]


@_skip_no_db
def test_calculate_score_knu_course_excellence_uses_course400_plus_review100() -> None:
    result = calculate_score("22", _arts_pe_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KNU_2027_STUDENT_COURSE400_COMPLETION_REVIEW100"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["record_full_score"] == pytest.approx(500.0)
    assert result["practical_full_score"] == pytest.approx(100.0)
    assert result["full_practical_total"] == pytest.approx(500.0)
    assert result["used_subjects"] == 5


@_skip_no_db
def test_calculate_score_knu_pe_education_practical_uses_course200_plus_practical300() -> None:
    result = calculate_score("29", _arts_pe_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == "KNU_2027_PE_EDU_PRACTICAL_COURSE200_PRACTICAL300"
    assert result["student_record_score"] == pytest.approx(200.0)
    assert result["record_full_score"] == pytest.approx(200.0)
    assert result["practical_full_score"] == pytest.approx(300.0)
    assert result["full_practical_total"] == pytest.approx(500.0)


@_skip_no_db
def test_calculate_score_knu_pe_major_practical_uses_course150_plus_practical350() -> None:
    result = calculate_score("34", _arts_pe_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == "KNU_2027_SPORT_SCIENCE_PRACTICAL_COURSE150_PRACTICAL350"
    assert result["student_record_score"] == pytest.approx(150.0)
    assert result["record_full_score"] == pytest.approx(150.0)
    assert result["practical_full_score"] == pytest.approx(350.0)
    assert result["full_practical_total"] == pytest.approx(500.0)


@_skip_no_db
def test_calculate_score_knu_student_comprehensive_is_non_calculation_track() -> None:
    result = calculate_score("24", _arts_pe_subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KNU_2027_STUDENT_RECORD_DOCUMENT_REVIEW_100"
