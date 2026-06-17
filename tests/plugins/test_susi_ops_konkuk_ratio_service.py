from __future__ import annotations

import pytest

from plugins.susi_ops.service import _student_grades_from_central, calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


@_skip_no_db
def test_calculate_score_konkuk_glocal_uses_life_record_achievement_ratios() -> None:
    name, grades = _student_grades_from_central("박시현")
    attendance = {"unexcused_absence_days": 7, "unexcused_late": 1, "unexcused_early_leave": 3}

    assert name == "박시현"
    assert any(row.get("과목") == "수학과제 탐구" and row.get("achievement_ratios") for row in grades)

    for uid in ["9", "10"]:
        result = calculate_score(uid, grades, attendance, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "weighted_grade_table"
        assert result["student_record_score"] == pytest.approx(110.8511)
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
