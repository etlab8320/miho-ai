from __future__ import annotations

import pytest

from plugins.susi_ops.service import _student_grades_from_central, calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

PRACTICAL_FORMULA_KEY = "YIU_2027_ARTSPORT_TOP3_PER_GRADE_DISTINCT_COURSE_RECORD30_FITNESS70"
SPECIAL_PE_EDUCATION_FORMULA_KEY = "YIU_2027_TEACHER_TOP4_PER_GRADE_DISTINCT_COURSE_RECORD30_FITNESS70"
RECORD100_FORMULA_KEY = "YIU_2027_ARTSPORT_TOP3_PER_GRADE_DISTINCT_COURSE_RECORD100"


def _subjects() -> list[dict[str, object]]:
    rows = []
    for grade in (1, 2, 3):
        for group in ("국어", "영어", "수학"):
            rows.append({
                "학년": grade,
                "학기": 1,
                "교과": group,
                "과목": f"{group}{grade}",
                "이수단위": 3,
                "등급": "1",
                "과목구분": "일반",
            })
    return rows


def _subjects_with_grade3_semester2_bonus() -> list[dict[str, object]]:
    rows = []
    for grade in (1, 2):
        for group in ("국어", "영어", "수학"):
            rows.append({
                "학년": grade,
                "학기": 1,
                "교과": group,
                "과목": f"{group}{grade}",
                "이수단위": 3,
                "등급": "1",
                "과목구분": "일반",
            })
    rows.extend([
        {"학년": 3, "학기": 1, "교과": "국어", "과목": "국어3", "이수단위": 3, "등급": "1", "과목구분": "일반"},
        {"학년": 3, "학기": 1, "교과": "영어", "과목": "영어3", "이수단위": 3, "등급": "1", "과목구분": "일반"},
        {"학년": 3, "학기": 1, "교과": "수학", "과목": "졸업예정저점", "이수단위": 3, "등급": "9", "과목구분": "일반"},
        {"학년": 3, "학기": 2, "교과": "사회", "과목": "졸업자3-2고점", "이수단위": 3, "등급": "1", "과목구분": "일반"},
    ])
    return rows


def _subjects_four_distinct_groups_per_grade() -> list[dict[str, object]]:
    rows = []
    for grade in (1, 2, 3):
        for group in ("국어", "영어", "수학", "사회"):
            rows.append({
                "학년": grade,
                "학기": 1,
                "교과": group,
                "과목": f"{group}{grade}",
                "이수단위": 3,
                "등급": "1",
                "과목구분": "일반",
            })
    return rows


@_skip_no_db
def test_calculate_score_yongin_practical_uses_official_formula_plugin() -> None:
    result = calculate_score("276", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == PRACTICAL_FORMULA_KEY
    assert result["used_subjects"] == 9
    assert result["student_record_score"] == pytest.approx(150.0)
    assert result["record_full_score"] == pytest.approx(150.0)
    assert result["practical_full_score"] == pytest.approx(350.0)
    assert result["full_practical_total"] == pytest.approx(500.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_yongin_special_pe_education_uses_teacher_track_12_subjects() -> None:
    result = calculate_score("284", _subjects_four_distinct_groups_per_grade(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == SPECIAL_PE_EDUCATION_FORMULA_KEY
    assert result["used_subjects"] == 12
    assert result["student_record_score"] == pytest.approx(150.0)
    assert result["record_full_score"] == pytest.approx(150.0)
    assert result["practical_full_score"] == pytest.approx(350.0)
    assert result["full_practical_total"] == pytest.approx(500.0)


@_skip_no_db
def test_calculate_score_yongin_special_pe_education_handles_park_missing_subjects_by_guide() -> None:
    name, grades = _student_grades_from_central("박시현")

    opportunity = calculate_score("283", grades, {}, {})
    general = calculate_score("284", grades, {}, {})

    assert name == "박시현"
    assert opportunity["status"] == "calculated"
    assert general["status"] == "calculated"
    assert opportunity["formula_key"] == SPECIAL_PE_EDUCATION_FORMULA_KEY
    assert general["formula_key"] == SPECIAL_PE_EDUCATION_FORMULA_KEY
    assert opportunity["student_record_score"] == pytest.approx(88.125)
    assert general["student_record_score"] == pytest.approx(84.375)
    assert opportunity["used_subjects"] > 0
    assert general["used_subjects"] > 0


@_skip_no_db
def test_calculate_score_yongin_practical_graduate_context_includes_grade3_semester2() -> None:
    current = calculate_score("276", _subjects_with_grade3_semester2_bonus(), {}, {}, {"is_graduate": False})
    graduate = calculate_score("276", _subjects_with_grade3_semester2_bonus(), {}, {}, {"is_graduate": True})

    assert current["status"] == "calculated"
    assert graduate["status"] == "calculated"
    assert current["student_record_score"] < graduate["student_record_score"]


@_skip_no_db
def test_calculate_score_yongin_record100_rows_are_calculated() -> None:
    result = calculate_score("290", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == RECORD100_FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(500.0)
    assert result["record_full_score"] == pytest.approx(500.0)
    assert result["practical_full_score"] == pytest.approx(0.0)
    assert result["full_practical_total"] == pytest.approx(500.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_yongin_school_violence_measures_are_summed() -> None:
    result = calculate_score(
        "276",
        _subjects(),
        {"practical_event_scores": [170, 165], "school_violence_measures": [4, 8]},
        {},
    )

    assert result["status"] == "calculated"
    assert result["practical_full_score"] == pytest.approx(335.0)
    assert result["full_practical_total"] == pytest.approx(425.0)


@_skip_no_db
def test_calculate_score_yongin_practical_absence_is_ineligible() -> None:
    result = calculate_score("276", _subjects(), {"practical_absent": True}, {})

    assert result["status"] == "practical_absent_ineligible"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == PRACTICAL_FORMULA_KEY
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
