from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path


_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _grade_one_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "통합사회", "이수단위": 3, "등급": "1"},
    ]


def _truncation_boundary_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어2", "이수단위": 5, "등급": "2"},
    ]


@_skip_no_db
def test_calculate_score_kyonggi_sports_science_keeps_official_30_70_contract() -> None:
    result = calculate_score("16", _grade_one_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KYONGGI_2027_OFFICIAL_SPORTS_SCIENCE_RECORD30_PRACTICAL70"
    assert result["student_record_score"] == pytest.approx(30.0)
    assert result["record_full_score"] == pytest.approx(30.0)
    assert result["practical_full_score"] == pytest.approx(70.0)
    assert result["full_practical_total"] == pytest.approx(100.0)


@_skip_no_db
def test_calculate_score_kyonggi_pe_department_uses_official_40_60_contract() -> None:
    result = calculate_score("418", _grade_one_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KYONGGI_2027_OFFICIAL_PE_DEPT_RECORD40_PRACTICAL60"
    assert result["student_record_score"] == pytest.approx(40.0)
    assert result["record_full_score"] == pytest.approx(40.0)
    assert result["practical_full_score"] == pytest.approx(60.0)
    assert result["full_practical_total"] == pytest.approx(100.0)


@_skip_no_db
def test_calculate_score_kyonggi_truncates_each_record_calculation_step() -> None:
    result = calculate_score("16", _truncation_boundary_subjects(), {"practical_score": 0}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(29.749)
    assert result["full_practical_total"] == pytest.approx(29.749)
