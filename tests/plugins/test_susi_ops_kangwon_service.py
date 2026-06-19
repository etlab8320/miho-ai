from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "KANGWON_2027_CHUNCHEON_PRACTICAL_RECORD1000_PRACTICAL600"


@_skip_no_db
def test_calculate_score_kangwon_physical_education_excludes_korean_history_from_record() -> None:
    subjects = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "통합사회", "이수단위": 3, "등급": "9"},
        {"학년": 1, "학기": 1, "교과": "체육", "과목": "체육", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": "1"},
    ]

    result = calculate_score("8", subjects, {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(820.0)
    assert result["record_full_score"] == pytest.approx(1000.0)
    assert result["practical_full_score"] == pytest.approx(600.0)


@_skip_no_db
def test_calculate_score_kangwon_sports_science_reflects_korean_english_pe_only() -> None:
    subjects = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "체육", "과목": "체육", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "통합사회", "이수단위": 3, "등급": "9"},
    ]

    result = calculate_score("7", subjects, {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(1000.0)
    assert result["record_full_score"] == pytest.approx(1000.0)
    assert result["practical_full_score"] == pytest.approx(600.0)
    assert result["full_practical_total"] == pytest.approx(1600.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_kangwon_school_violence_measure_4_deducts_five_percent() -> None:
    subjects = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "체육", "과목": "체육", "이수단위": 3, "등급": "1"},
    ]

    result = calculate_score("7", subjects, {"school_violence_measure": 4}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(1000.0)
    assert result["full_practical_total"] == pytest.approx(1520.0)
