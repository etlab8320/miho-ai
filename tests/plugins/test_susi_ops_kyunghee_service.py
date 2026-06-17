from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _khu_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 2, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "국어", "과목": "국어2", "이수단위": 2, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 2, "등급": "1"},
        {"학년": 2, "학기": 2, "교과": "영어", "과목": "영어2", "이수단위": 2, "등급": "1"},
        {"학년": 3, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 1, "성취도": "A", "과목구분": "진로선택"},
        {"학년": 3, "학기": 1, "교과": "영어", "과목": "진로영어", "이수단위": 1, "성취도": "A", "과목구분": "진로선택"},
    ]


@_skip_no_db
def test_calculate_score_kyunghee_regional_uses_official_formula_plugin() -> None:
    result = calculate_score(
        "63",
        _khu_subjects(),
        {"unexcused_absence_days": 0, "service_hours": 15},
        {},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KHU_2027_ARTSPORT_REGIONAL_KOREAN_ENGLISH_ALL_CAREER_TOP3_COURSE560_ATTEND_SERVICE140_REVIEW300"
    assert result["student_record_score"] == pytest.approx(700.0)
    assert result["used_subjects"] == 6
    assert result["total_units"] == pytest.approx(10.0)


@_skip_no_db
def test_calculate_score_kyunghee_neorenaissance_stays_non_calculation() -> None:
    result = calculate_score("58", _khu_subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KHU_2027_NON_CALCULATION_TRACK"


@_skip_no_db
def test_calculate_score_kyunghee_not_in_official_guide_is_blocked() -> None:
    result = calculate_score("59", _khu_subjects(), {"service_hours": 15}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KHU_2027_NOT_IN_OFFICIAL_GUIDE"
