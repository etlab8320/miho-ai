from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "WOOSONG_2027_OFFICIAL_RECORD_ATTENDANCE_BONUS"
NON_CALC_KEY = "WOOSONG_2027_STUDENT_RECORD_COMPREHENSIVE_NON_CALCULATION"


def _subjects() -> list[dict[str, object]]:
    base = [
        (1, 1, "국어", "국어1", 8),
        (1, 2, "한문", "한문1", 1),
        (1, 1, "수학", "수학1", 8),
        (1, 2, "영어", "영어1", 8),
        (1, 1, "사회", "사회1", 1),
        (1, 2, "한국사", "한국사1", 1),
        (2, 1, "과학", "과학1", 1),
        (2, 1, "국어", "국어2", 8),
        (2, 1, "수학", "수학2", 8),
        (2, 2, "영어", "영어2", 8),
        (3, 1, "사회", "사회2", 1),
        (3, 1, "과학", "과학2", 1),
    ]
    rows = [
        {
            "학년": grade,
            "학기": semester,
            "교과": group,
            "과목": subject,
            "이수단위": unit,
            "등급": "1",
            "과목구분": "일반",
        }
        for grade, semester, group, subject, unit in base
    ]
    rows.extend([
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로A1", "이수단위": 1, "성취도": "A", "과목구분": "진로"},
        {"학년": 2, "학기": 2, "교과": "영어", "과목": "진로A2", "이수단위": 1, "성취도": "A", "과목구분": "진로"},
    ])
    return rows


@_skip_no_db
def test_calculate_score_woosong_12_subject_tracks_use_official_formula_plugin() -> None:
    for university_id in ("301", "302", "305", "311", "313"):
        result = calculate_score(university_id, _subjects(), {}, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == FORMULA_KEY
        assert result["used_subjects"] == 12
        assert result["student_record_score"] == pytest.approx(1000.0)
        assert result["record_full_score"] == pytest.approx(1000.0)
        assert result["practical_full_score"] == pytest.approx(0.0)
        assert result["full_practical_total"] == pytest.approx(1000.0)
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_woosong_course_interview_uses_6_subject_contract() -> None:
    result = calculate_score("306", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["used_subjects"] == 6
    assert result["student_record_score"] == pytest.approx(800.0)
    assert result["record_full_score"] == pytest.approx(800.0)
    assert result["practical_full_score"] == pytest.approx(200.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_woosong_attendance_and_school_violence_are_applied_after_total() -> None:
    result = calculate_score("301", _subjects(), {"unexcused_absence_days": 5, "school_violence_measures": [4, 8]}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(994.0)
    assert result["full_practical_total"] == pytest.approx(974.0)


@_skip_no_db
def test_calculate_score_woosong_comprehensive_tracks_are_non_calculation() -> None:
    for university_id in ("307", "309"):
        result = calculate_score(university_id, _subjects(), {}, {})

        assert result["status"] == "non_calculation_track"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == NON_CALC_KEY
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
