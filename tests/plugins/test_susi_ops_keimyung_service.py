from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for grade, semester in [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1)]:
        rows.append({"학년": grade, "학기": semester, "교과": "국어", "과목": f"국어{grade}{semester}", "이수단위": 1, "등급": "1"})
        rows.append({"학년": grade, "학기": semester, "교과": "영어", "과목": f"영어{grade}{semester}", "이수단위": 1, "등급": "1"})
        rows.append({"학년": grade, "학기": semester, "교과": "사회", "과목": f"사회{grade}{semester}", "이수단위": 1, "등급": "1"})
    rows.extend(
        [
            {"학년": 1, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 3, "성취도": "A", "과목구분": "진로"},
            {"학년": 2, "학기": 1, "교과": "영어", "과목": "진로영어", "이수단위": 3, "성취도": "A", "과목구분": "진로"},
            {"학년": 3, "학기": 1, "교과": "사회", "과목": "진로사회", "이수단위": 3, "성취도": "A", "과목구분": "진로"},
        ]
    )
    return rows


@_skip_no_db
def test_calculate_score_keimyung_regional_uses_course_career_attendance_split() -> None:
    result = calculate_score("78", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KEIMYUNG_2027_OFFICIAL_RECORD_ATTENDANCE_CAREER"
    assert result["student_record_score"] == pytest.approx(100.0)
    assert result["record_full_score"] == pytest.approx(100.0)
    assert result["practical_full_score"] == pytest.approx(0.0)
    assert result["full_practical_total"] == pytest.approx(100.0)


@_skip_no_db
def test_calculate_score_keimyung_student_comprehensive_is_non_calculation_track() -> None:
    general = calculate_score("76", _subjects(), {}, {})
    regional = calculate_score("83", _subjects(), {}, {})

    assert general["status"] == "non_calculation_track"
    assert general["strategy"] == "official_formula_plugin"
    assert general["formula_key"] == "KEIMYUNG_2027_NON_CALCULATION_TRACK"
    assert regional["status"] == "non_calculation_track"
    assert regional["strategy"] == "official_formula_plugin"
    assert regional["formula_key"] == "KEIMYUNG_2027_NON_CALCULATION_TRACK"
