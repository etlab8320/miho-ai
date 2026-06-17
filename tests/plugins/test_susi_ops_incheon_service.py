from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

SPORTSCI_KEY = "INU_2027_SPORTSCI_PRACTICAL_KOR40_ENG30_SOC30_ALLSUBJ_CREDITWEIGHTED_GRADE200BASE_TO_3_1_CAREER_NA"
SPORTMED_KEY = "INU_2027_SPORTSMED_PRACTICAL_KOR40_ENG30_SOCorSCI_TOPGROUP30_CREDITWEIGHTED_GRADE200BASE_TO_3_1_GASAN05_CAREER_NA"
PE_KEY = "INU_2027_PEEDU_PRACTICAL_KOR40_ENG30_SOC30_ALLSUBJ_CREDITWEIGHTED_GRADE200BASE_TO_3_1_INTERVIEW20_CAREER_NA"
SELFREC_KEY = "INU_2027_SPORTSMED_SELFREC_DOC100_4X_THEN_DOC70_INTERVIEW30_NONCALC"


def _subjects(social_grade: str = "1") -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회", "이수단위": 3, "등급": social_grade, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "과학", "과목": "과학", "이수단위": 3, "등급": "1", "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "과학", "과목": "진로과학", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        {"학년": 2, "학기": 1, "교과": "수학", "과목": "제외수학", "이수단위": 9, "등급": "9", "과목구분": "일반"},
    ]


@_skip_no_db
def test_calculate_score_incheon_sports_science_uses_official_formula_plugin() -> None:
    result = calculate_score("312", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == SPORTSCI_KEY
    assert result["used_subjects"] == 3
    assert result["student_record_score"] == pytest.approx(200.0)
    assert result["record_full_score"] == pytest.approx(200.0)
    assert result["practical_full_score"] == pytest.approx(300.0)
    assert result["full_practical_total"] == pytest.approx(500.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_incheon_sports_medicine_counts_career_units_for_bonus() -> None:
    result = calculate_score("315", _subjects(social_grade="9"), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == SPORTMED_KEY
    assert result["used_subjects"] == 3
    assert result["student_record_score"] == pytest.approx(200.55)
    assert result["full_practical_total"] == pytest.approx(500.55)


@_skip_no_db
def test_calculate_score_incheon_pe_education_includes_interview_full_score() -> None:
    result = calculate_score("316", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == PE_KEY
    assert result["student_record_score"] == pytest.approx(200.0)
    assert result["practical_full_score"] == pytest.approx(300.0)
    assert result["full_practical_total"] == pytest.approx(500.0)
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(300.0)
    assert result["vs_prev_year"]["reachable_at_full_practical"] is True
    assert "warning" not in result["vs_prev_year"]


@_skip_no_db
def test_calculate_score_incheon_practical_absence_and_selfrec_non_calculation() -> None:
    absent = calculate_score("312", _subjects(), {"practical_absent": True}, {})
    selfrec = calculate_score("322", _subjects(), {}, {})

    assert absent["status"] == "practical_absent_ineligible"
    assert absent["formula_key"] == SPORTSCI_KEY
    assert selfrec["status"] == "non_calculation_track"
    assert selfrec["formula_key"] == SELFREC_KEY
    assert selfrec["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
