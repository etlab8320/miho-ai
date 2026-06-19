from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": f"국어{i}", "이수단위": 3, "등급": "1"}
        for i in range(8)
    ]


@_skip_no_db
def test_calculate_score_geukdong_uses_official_formula_and_counts_only_subjects() -> None:
    result = calculate_score("105", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "GEUKDONG_2027_SPORTS_REHAB_GENERAL_RECORD400_PRACTICAL600"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["used_subjects"] == 8


@_skip_no_db
def test_calculate_score_geukdong_graduate_includes_grade3_semester2() -> None:
    subjects = [
        {"학년": 3, "학기": 1, "교과": "국어", "과목": f"저점{i}", "이수단위": 3, "등급": "9"}
        for i in range(8)
    ]
    subjects.append({"학년": 3, "학기": 2, "교과": "국어", "과목": "졸업자고점", "이수단위": 3, "등급": "1"})

    current = calculate_score("105", subjects, {"unexcused_absence_days": 0}, {}, {"is_graduate": False})
    graduate = calculate_score("105", subjects, {"unexcused_absence_days": 0}, {}, {"is_graduate": True})

    assert current["status"] == "calculated"
    assert graduate["status"] == "calculated"
    assert current["student_record_score"] == pytest.approx(272.0)
    assert graduate["student_record_score"] == pytest.approx(288.0)
