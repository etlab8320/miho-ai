from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "과학", "과목": "과학", "이수단위": 3, "등급": rank, "과목구분": "일반"},
    ]


@_skip_no_db
def test_calculate_score_sunchon_uses_official_formula_plugin() -> None:
    result = calculate_score("256", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SUNCHON_2027_PRACTICAL_RECORD250_PRACTICAL750"
    assert result["student_record_score"] == pytest.approx(250.0)
    assert result["record_full_score"] == pytest.approx(250.0)
    assert result["practical_full_score"] == pytest.approx(750.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_sunchon_graduate_context_includes_third_grade_second_semester() -> None:
    subjects = _subjects()
    subjects.append({"학년": 3, "학기": 2, "교과": "국어", "과목": "3-2국어", "이수단위": 30, "등급": "9", "과목구분": "일반"})

    regular = calculate_score("256", subjects, {"practical_score": 100}, {})
    graduate = calculate_score("256", subjects, {"practical_score": 100}, {}, {"is_graduate": True})

    assert regular["student_record_score"] == pytest.approx(250.0)
    assert graduate["student_record_score"] == pytest.approx(83.93)
    assert graduate["full_practical_total"] == pytest.approx(183.93)


@_skip_no_db
def test_calculate_score_sunchon_school_violence_uses_highest_deduction() -> None:
    result = calculate_score("256", _subjects(), {"school_violence_measures": [1, 4, 8]}, {})

    assert result["status"] == "calculated"
    assert result["full_practical_total"] == pytest.approx(800.0)
