from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": rank, "과목구분": "일반"},
    ]


@_skip_no_db
def test_calculate_score_yeungnam_sports_practical_uses_official_formula_plugin() -> None:
    result = calculate_score("270", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "YEUNGNAM_2027_SPORTS_PRACTICAL_COURSE288_ATT16_EFFORT16_PRACTICAL480"
    assert result["student_record_score"] == pytest.approx(320.0)
    assert result["record_full_score"] == pytest.approx(320.0)
    assert result["practical_full_score"] == pytest.approx(480.0)
    assert result["full_practical_total"] == pytest.approx(800.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_yeungnam_adapted_pe_exposes_minimum_csat() -> None:
    result = calculate_score("288", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "YEUNGNAM_2027_GENERAL_COURSE720_ATT40_EFFORT40"
    assert result["student_record_score"] == pytest.approx(800.0)
    assert result["record_full_score"] == pytest.approx(800.0)
    assert result["practical_full_score"] == pytest.approx(0.0)
    assert result["full_practical_total"] == pytest.approx(800.0)
    assert result["minimum_csat"] == {"has_minimum": True, "detail": "상위 2개영역 합 9 이내"}


@_skip_no_db
def test_calculate_score_yeungnam_school_violence_uses_highest_measure() -> None:
    result = calculate_score("270", _subjects(), {"school_violence_measures": [1, 4, 8]}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(320.0)
    assert result["full_practical_total"] == pytest.approx(750.0)
