from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 2, "학기": 2, "교과": "사회", "과목": "사회", "이수단위": 3, "등급": "1"},
        {"학년": 3, "학기": 1, "교과": "과학", "과목": "과학", "이수단위": 3, "등급": "1"},
    ]


@_skip_no_db
def test_calculate_score_gongju_uses_official_formula_plugin() -> None:
    result = calculate_score("99", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "GONGJU_2027_SPORT_SCIENCE_GENERAL_RECORD30_PRACTICAL70"
    assert result["student_record_score"] == pytest.approx(300.0)


@_skip_no_db
def test_calculate_score_gongju_physical_education_rural_uses_same_official_formula() -> None:
    result = calculate_score("100", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "GONGJU_2027_PHYSICAL_ED_GENERAL_RURAL_RECORD70_PRACTICAL30"
    assert result["student_record_score"] == pytest.approx(700.0)
    assert result["record_full_score"] == pytest.approx(703.5)
    assert result["practical_full_score"] == pytest.approx(300.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_gongju_applies_school_violence_total_deduction() -> None:
    result = calculate_score("101", _subjects(), {"school_violence_measures": [2]}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(700.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(980.0)
