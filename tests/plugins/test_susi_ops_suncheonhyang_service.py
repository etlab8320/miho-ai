from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

_MINIMUM_CSAT = "국어, 수학, 영어 중 우수 1개 영역 3등급 이내"


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    rows = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 5, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 2, "교과": "영어", "과목": "영어", "이수단위": 5, "등급": rank, "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 5, "등급": rank, "과목구분": "일반"},
        {"학년": 2, "학기": 2, "교과": "사회", "과목": "사회", "이수단위": 5, "등급": rank, "과목구분": "일반"},
        {"학년": 3, "학기": 1, "교과": "과학", "과목": "과학", "이수단위": 5, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 5, "등급": rank, "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "심화국어", "이수단위": 5, "성취도": "A", "과목구분": "진로"},
    ]
    return rows


@_skip_no_db
def test_calculate_score_suncheonhyang_practical_uses_official_formula_plugin() -> None:
    result = calculate_score("257", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SCH_2027_PRACTICAL_RECORD30_PRACTICAL70"
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["record_full_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_suncheonhyang_course_excellence_has_minimum_csat() -> None:
    result = calculate_score("267", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == "SCH_2027_COURSE_EXCELLENCE_RECORD1000"
    assert result["student_record_score"] == pytest.approx(1000.0)
    assert result["record_full_score"] == pytest.approx(1000.0)
    assert result["practical_full_score"] == pytest.approx(0.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": True, "detail": _MINIMUM_CSAT}


@_skip_no_db
def test_calculate_score_suncheonhyang_non_calculation_tracks_stay_blocked() -> None:
    not_in_guide = calculate_score("260", _subjects(), {}, {})
    comprehensive = calculate_score("266", _subjects(), {}, {})

    assert not_in_guide["status"] == "non_calculation_track"
    assert not_in_guide["formula_key"] == "SCH_2027_SPORTS_MEDICINE_NOT_IN_OFFICIAL_PRACTICAL_GUIDE"
    assert not_in_guide["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
    assert comprehensive["status"] == "non_calculation_track"
    assert comprehensive["formula_key"] == "SCH_2027_STUDENT_COMPREHENSIVE_DOCUMENT100_NON_CALCULATION"
    assert comprehensive["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
