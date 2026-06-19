from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "JEJU_2027_OFFICIAL_COURSE_GROUPS_PRACTICAL"


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 4, "등급": "1", "과목구분": "공통"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 4, "등급": "1", "과목구분": "공통"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 4, "등급": "1", "과목구분": "공통"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "통합사회", "이수단위": 3, "등급": "1", "과목구분": "공통"},
        {"학년": 1, "학기": 1, "교과": "과학", "과목": "통합과학", "이수단위": 3, "등급": "1", "과목구분": "공통"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "문학", "이수단위": 4, "등급": "1", "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "영어I", "이수단위": 4, "등급": "1", "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "사회", "과목": "생활과윤리", "이수단위": 3, "등급": "1", "과목구분": "일반"},
        {"학년": 3, "학기": 1, "교과": "국어", "과목": "심화국어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        {"학년": 3, "학기": 1, "교과": "영어", "과목": "진로영어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        {"학년": 3, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 20, "등급": "1", "과목구분": "일반"},
    ]


@_skip_no_db
def test_calculate_score_jeju_sports_science_contract() -> None:
    result = calculate_score("324", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(900.0)
    assert result["record_full_score"] == pytest.approx(900.0)
    assert result["practical_full_score"] == pytest.approx(100.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"]["has_minimum"] is True
    assert "2개 영역 등급 합 10" in result["minimum_csat"]["detail"]


@_skip_no_db
def test_calculate_score_jeju_physical_education_and_absence() -> None:
    result = calculate_score("326", _subjects(), {}, {})
    absent = calculate_score("326", _subjects(), {"practical_absent": True}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(850.0)
    assert result["practical_full_score"] == pytest.approx(150.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert "2개 영역 등급 합 8" in result["minimum_csat"]["detail"]
    assert absent["status"] == "jeju_practical_absent_ineligible"


@_skip_no_db
def test_calculate_score_jeju_physical_education_practical_events_have_no_multiplier() -> None:
    result = calculate_score(
        "326",
        _subjects(),
        {
            "practical_event_scores": {
                "20m왕복달리기": 40,
                "서서 윗몸 앞으로 굽히기": 40,
                "농구": 40,
            },
        },
        {},
    )

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(850.0)
    assert result["practical_full_score"] == pytest.approx(120.0)
    assert result["full_practical_total"] == pytest.approx(970.0)


@_skip_no_db
def test_calculate_score_jeju_not_in_guide_row_is_blocked() -> None:
    result = calculate_score("325", _subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["formula_key"] == "JEJU_2027_NOT_IN_OFFICIAL_GUIDE"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "공식 2027 수시모집요강 모집 없음"}
