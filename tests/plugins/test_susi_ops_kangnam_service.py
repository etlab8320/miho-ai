from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path


_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _grade9_subjects_with_grade3_semester2_bonus() -> list[dict[str, object]]:
    subjects = [
        {
            "학년": 3,
            "학기": 1,
            "교과": "국어",
            "과목": f"졸업예정저점{index}",
            "이수단위": 1,
            "등급": "9",
        }
        for index in range(20)
    ]
    subjects.append(
        {
            "학년": 3,
            "학기": 2,
            "교과": "국어",
            "과목": "졸업자추가고점",
            "이수단위": 1,
            "등급": "1",
        }
    )
    return subjects


@_skip_no_db
def test_calculate_score_kangnam_graduate_context_includes_grade3_semester2() -> None:
    subjects = _grade9_subjects_with_grade3_semester2_bonus()

    current = calculate_score("5", subjects, {}, {}, {"is_graduate": False})
    graduate = calculate_score("5", subjects, {}, {}, {"is_graduate": True})

    assert current["status"] == "calculated"
    assert graduate["status"] == "calculated"
    assert current["student_record_score"] == pytest.approx(0.0)
    assert graduate["student_record_score"] == pytest.approx(10.0)
    assert graduate["full_practical_total"] == pytest.approx(810.0)
