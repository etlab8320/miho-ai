from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path
from plugins.susi_ops.rules import lookup_rules

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in ["국어", "영어", "수학", "사회"]:
        rows.append({"학년": 1, "학기": 1, "교과": group, "과목": f"{group}1", "이수단위": 1, "등급": "1", "과목구분": "일반"})
        rows.append({"학년": 1, "학기": 2, "교과": group, "과목": f"{group}2", "이수단위": 1, "등급": "1", "과목구분": "일반"})
    rows.append({"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 1, "성취도": "A", "과목구분": "진로"})
    rows.append({"학년": 2, "학기": 2, "교과": "영어", "과목": "진로영어", "이수단위": 1, "성취도": "A", "과목구분": "진로"})
    return rows


def _semester_limit_subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in ["국어", "영어", "수학"]:
        rows.append({"학년": 1, "학기": 1, "교과": group, "과목": f"{group}1", "이수단위": 1, "등급": "1", "과목구분": "일반"})
        rows.append({"학년": 1, "학기": 2, "교과": group, "과목": f"{group}2", "이수단위": 1, "등급": "1", "과목구분": "일반"})
    rows.extend([
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회고점", "이수단위": 1, "등급": "1", "과목구분": "일반"},
        {"학년": 3, "학기": 1, "교과": "사회", "과목": "재학생반영저점", "이수단위": 1, "등급": "9", "과목구분": "일반"},
        {"학년": 3, "학기": 2, "교과": "사회", "과목": "졸업자3-2고점", "이수단위": 1, "등급": "1", "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 1, "성취도": "A", "과목구분": "진로"},
        {"학년": 2, "학기": 2, "교과": "영어", "과목": "진로영어", "이수단위": 1, "성취도": "A", "과목구분": "진로"},
    ])
    return rows


@_skip_no_db
def test_calculate_score_hanseo_leisure_uses_official_formula_plugin() -> None:
    result = calculate_score("385", _subjects(), {"unexcused_absence_days": 7}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "HANSEO_2027_LEISURE_RECORD100_PRACTICAL900"
    assert result["student_record_score"] == pytest.approx(99.4)
    assert result["record_full_score"] == pytest.approx(100.0)
    assert result["practical_full_score"] == pytest.approx(900.0)
    assert result["full_practical_total"] == pytest.approx(999.4)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_hanseo_leisure_current_student_excludes_grade3_semester2() -> None:
    result = calculate_score("385", _semester_limit_subjects(), {"unexcused_absence_days": 0}, {}, {"is_graduate": False})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(97.3)


@_skip_no_db
def test_calculate_score_hanseo_leisure_graduate_includes_grade3_semester2() -> None:
    result = calculate_score("385", _semester_limit_subjects(), {"unexcused_absence_days": 0}, {}, {"is_graduate": True})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(100.0)


@_skip_no_db
def test_calculate_score_hanseo_security_uses_practical_based_record_table() -> None:
    result = calculate_score("384", _subjects(), {"practical_score": 380, "interview_score": 260}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "HANSEO_2027_SECURITY_RECORD_BY_PRACTICAL500_INTERVIEW300"
    assert result["student_record_score"] == pytest.approx(160.0)
    assert result["record_full_score"] == pytest.approx(200.0)
    assert result["practical_full_score"] == pytest.approx(380.0)
    assert result["full_practical_total"] == pytest.approx(800.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_lookup_rules_hanseo_leisure_career_conversion_matches_official_points() -> None:
    rows = lookup_rules(university="한서대학교", department="레저해양", detail=True)["rows"]
    row = next(item for item in rows if item["university_id"] == "385")

    assert row["score_logic"]["career_conversion"] == {"A": 9.5, "B": 6.5, "C": 3.0}
