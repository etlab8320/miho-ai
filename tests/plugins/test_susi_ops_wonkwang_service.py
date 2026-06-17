from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

PRACTICAL_FORMULA_KEY = "WONKWANG_2027_PRACTICAL_RECORD600_PRACTICAL1000"
NON_CALC_FORMULA_KEY = "WONKWANG_2027_STUDENT_COMPREHENSIVE_NON_CALCULATION"
PE_MINIMUM_DETAIL = "국어, 수학, 영어, 과학/사회/직업탐구(2과목 평균) 중 상위 3개 영역 등급합 14 이내"


def _subjects() -> list[dict[str, object]]:
    rows = []
    for grade, semester, group, subject, unit in [
        (1, 1, "국어", "국어1", 3),
        (1, 2, "영어", "영어1", 3),
        (2, 1, "수학", "수학1", 4),
        (2, 2, "사회", "한국사1", 3),
        (3, 1, "과학", "과학1", 2),
    ]:
        rows.append({
            "학년": grade,
            "학기": semester,
            "교과": group,
            "과목": subject,
            "이수단위": unit,
            "등급": "1",
            "과목구분": "일반",
        })
    rows.extend([
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        {"학년": 3, "학기": 1, "교과": "영어", "과목": "진로영어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        {"학년": 3, "학기": 2, "교과": "수학", "과목": "제외수학", "이수단위": 8, "등급": "9", "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "체육", "과목": "제외체육", "이수단위": 8, "등급": "9", "과목구분": "일반"},
    ])
    return rows


@_skip_no_db
def test_calculate_score_wonkwang_sports_science_uses_official_formula_plugin() -> None:
    result = calculate_score("304", _subjects(), {"unexcused_absence_days": 7}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == PRACTICAL_FORMULA_KEY
    assert result["used_subjects"] == 7
    assert result["total_units"] == pytest.approx(19.0)
    assert result["student_record_score"] == pytest.approx(596.0)
    assert result["record_full_score"] == pytest.approx(600.0)
    assert result["practical_full_score"] == pytest.approx(1000.0)
    assert result["full_practical_total"] == pytest.approx(1596.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_wonkwang_pe_education_keeps_csat_minimum_contract() -> None:
    result = calculate_score("308", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == PRACTICAL_FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(600.0)
    assert result["full_practical_total"] == pytest.approx(1600.0)
    assert result["minimum_csat"] == {"has_minimum": True, "detail": PE_MINIMUM_DETAIL}


@_skip_no_db
def test_calculate_score_wonkwang_practical_score_and_school_violence_sum() -> None:
    result = calculate_score(
        "304",
        _subjects(),
        {
            "unexcused_absence_days": 0,
            "practical_event_scores": [400, 280, 260],
            "school_violence_measures": [3, 4],
        },
        {},
    )

    assert result["status"] == "calculated"
    assert result["practical_full_score"] == pytest.approx(940.0)
    assert result["full_practical_total"] == pytest.approx(1480.0)


@_skip_no_db
def test_calculate_score_wonkwang_student_comprehensive_is_non_calculation() -> None:
    result = calculate_score("314", _subjects(), {"unexcused_absence_days": 7}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == NON_CALC_FORMULA_KEY
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
