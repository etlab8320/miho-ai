from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path


_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


@_skip_no_db
def test_calculate_score_kyungnam_physical_education_uses_official_minimum_scale() -> None:
    subjects = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": f"국어{index}", "이수단위": 1, "등급": "9"}
        for index in range(10)
    ]

    result = calculate_score("21", subjects, {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KYUNGNAM_2027_OFFICIAL_RECORD_INTERVIEW_PRACTICAL"
    assert result["student_record_score"] == pytest.approx(384.0)
    assert result["record_full_score"] == pytest.approx(600.0)
    assert result["practical_full_score"] == pytest.approx(400.0)


@_skip_no_db
def test_calculate_score_kyungnam_graduate_includes_grade3_semester2() -> None:
    subjects = [
        {"학년": 3, "학기": 1, "교과": "국어", "과목": f"저점{index}", "이수단위": 1, "등급": "9"}
        for index in range(10)
    ]
    subjects.append({"학년": 3, "학기": 2, "교과": "국어", "과목": "졸업자고점", "이수단위": 1, "등급": "1"})

    current = calculate_score("21", subjects, {}, {}, {"is_graduate": False})
    graduate = calculate_score("21", subjects, {}, {}, {"is_graduate": True})

    assert current["status"] == "calculated"
    assert graduate["status"] == "calculated"
    assert current["student_record_score"] == pytest.approx(384.0)
    assert graduate["student_record_score"] == pytest.approx(405.6)
