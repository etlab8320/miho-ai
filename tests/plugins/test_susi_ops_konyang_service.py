from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "과학", "과목": "과학", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 1, "등급": "1"},
    ]


@_skip_no_db
def test_calculate_score_konyang_sports_medicine_record100_uses_official_plugin() -> None:
    result = calculate_score("12", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KONYANG_2027_SPORTS_MEDICINE_RECORD100"
    assert result["student_record_score"] == pytest.approx(100.0)
    assert result["record_full_score"] == pytest.approx(100.0)
    assert result["practical_full_score"] == pytest.approx(0.0)
    assert result["full_practical_total"] == pytest.approx(100.0)
    assert result["used_subjects"] == 6
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_konyang_practical_minimum_cutoff_uses_official_plugin() -> None:
    failed = calculate_score("14", _subjects(), {"practical_score": 320.3}, {})
    passed = calculate_score("14", _subjects(), {"practical_score": 320.4}, {})

    assert failed["strategy"] == "official_formula_plugin"
    assert failed["formula_key"] == "KONYANG_2027_REHAB_PT_PRACTICAL_RECORD20_PRACTICAL80"
    assert failed["status"] == "konyang_practical_below_minimum_ineligible"
    assert failed["student_record_score"] == pytest.approx(200.0)
    assert failed["practical_full_score"] == pytest.approx(320.3)
    assert failed["full_practical_total"] == pytest.approx(520.3)
    assert "실기 최저점 320.4점 미만" in failed["warnings"][0]

    assert passed["status"] == "calculated"
    assert passed["strategy"] == "official_formula_plugin"
    assert passed["student_record_score"] == pytest.approx(200.0)
    assert passed["practical_full_score"] == pytest.approx(320.4)
    assert passed["full_practical_total"] == pytest.approx(520.4)
