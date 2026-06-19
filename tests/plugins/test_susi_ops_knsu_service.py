from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "KNSU_2027_OFFICIAL_STAGE_SCORE"
MINIMUM_DETAIL = "국,수,영,탐(1과목) 중 상위 3개 영역 합 10등급 이내 / 한국사 필수응시"


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": group, "과목": group, "이수단위": 1, "등급": rank}
        for group in ["국어", "영어", "수학", "사회", "과학"]
    ]


def _semester_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "1학년", "이수단위": 1, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "2학년", "이수단위": 1, "등급": "1"},
        {"학년": 3, "학기": 1, "교과": "국어", "과목": "3학년1학기", "이수단위": 1, "등급": "1"},
        {"학년": 3, "학기": 2, "교과": "국어", "과목": "졸업자3학년2학기", "이수단위": 1, "등급": "9"},
    ]


@_skip_no_db
def test_calculate_score_knsu_uses_official_stage_formula_and_minimum() -> None:
    result = calculate_score("343", _subjects("3"), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(780.0)
    assert result["record_full_score"] == pytest.approx(800.0)
    assert result["practical_full_score"] == pytest.approx(200.0)
    assert result["full_practical_total"] == pytest.approx(980.0)
    assert result["minimum_csat"] == {"has_minimum": True, "detail": MINIMUM_DETAIL}


@_skip_no_db
def test_calculate_score_knsu_attendance_interview_and_ineligible_contracts() -> None:
    social = calculate_score("345", _subjects("3"), {"unexcused_absence_days": 7}, {})
    special = calculate_score("364", _subjects("1"), {"practical_score": 270, "interview_score": 80}, {})
    violence = calculate_score("343", _subjects("3"), {"school_violence_measure": 5}, {})
    absent = calculate_score("343", _subjects("3"), {"practical_absent": True}, {})

    assert social["student_record_score"] == pytest.approx(985.0)
    assert social["record_full_score"] == pytest.approx(1000.0)
    assert social["practical_full_score"] == pytest.approx(0.0)
    assert special["student_record_score"] == pytest.approx(600.0)
    assert special["full_practical_total"] == pytest.approx(950.0)
    assert violence["status"] == "knsu_school_violence_ineligible"
    assert violence["formula_key"] == FORMULA_KEY
    assert absent["status"] == "knsu_practical_absent_ineligible"
    assert absent["formula_key"] == FORMULA_KEY


@_skip_no_db
def test_calculate_score_knsu_special_pe_reflects_korean_history_subject() -> None:
    result = calculate_score(
        "364",
        [{"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 1, "등급": "1"}],
        {"practical_score": 300, "interview_score": 100},
        {},
    )

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(600.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)


@_skip_no_db
def test_calculate_score_knsu_semester_context_defaults_to_current_student() -> None:
    current = calculate_score("343", _semester_subjects(), {}, {})
    graduate = calculate_score("343", _semester_subjects(), {}, {}, {"is_graduate": True})

    assert current["student_record_score"] == pytest.approx(800.0)
    assert current["average_grade"] == pytest.approx(1.0)
    assert graduate["student_record_score"] == pytest.approx(780.0)
    assert graduate["average_grade"] == pytest.approx(2.6)
