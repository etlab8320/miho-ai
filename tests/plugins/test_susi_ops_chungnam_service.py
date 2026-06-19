from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _perfect_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": "1"},
    ]


@_skip_no_db
def test_calculate_score_chungnam_practical_general_includes_attendance_and_practical_full() -> None:
    result = calculate_score("415", _perfect_subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "weighted_grade_table"
    assert result["academic_record_score"] == pytest.approx(90.0)
    assert result["attendance_score"] == pytest.approx(10.0)
    assert result["student_record_score"] == pytest.approx(100.0)
    assert result["record_full_score"] == pytest.approx(100.0)
    assert result["practical_full_score"] == pytest.approx(200.0)
    assert result["full_practical_total"] == pytest.approx(300.0)
    assert result["minimum_csat"]["detail"] == "수능 최저학력기준 미적용"


@_skip_no_db
def test_calculate_score_chungnam_attendance_band_reduces_student_record_score() -> None:
    result = calculate_score("415", _perfect_subjects(), {"unexcused_absence_days": 10}, {})

    assert result["academic_record_score"] == pytest.approx(90.0)
    assert result["attendance_absence_days"] == pytest.approx(10.0)
    assert result["attendance_score"] == pytest.approx(6.0)
    assert result["student_record_score"] == pytest.approx(96.0)
    assert result["full_practical_total"] == pytest.approx(296.0)


@_skip_no_db
def test_calculate_score_chungnam_uses_unit_weighted_grade_points() -> None:
    subjects = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 1, "등급": "3"},
    ]

    result = calculate_score("415", subjects, {"unexcused_absence_days": 0}, {})

    assert result["academic_record_score"] == pytest.approx(87.5)
    assert result["attendance_score"] == pytest.approx(10.0)
    assert result["student_record_score"] == pytest.approx(97.5)
