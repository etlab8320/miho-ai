from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, (grade, semester) in enumerate([(1, 1), (1, 2), (2, 1), (2, 2), (3, 1)]):
        rows.append({"학년": grade, "학기": semester, "교과": "국어", "과목": f"국어{index}", "이수단위": 3, "등급": "1"})
        rows.append({"학년": grade, "학기": semester, "교과": "영어", "과목": f"영어{index}", "이수단위": 3, "등급": "1"})
    return rows


def _central_generic_subjects() -> list[dict[str, object]]:
    rows = []
    for subject in _subjects():
        rows.append({**subject, "교과": "일반", "과목구분": "일반"})
    return rows


@_skip_no_db
def test_calculate_score_sangji_practical_track_uses_official_plugin() -> None:
    result = calculate_score("219", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SANGJI_2027_PRACTICAL_COURSE300_ATTENDANCE_TOTAL_DEDUCTION_PRACTICAL700"
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["record_full_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["used_subjects"] == 10
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_sangji_infers_subject_area_from_generic_central_category() -> None:
    result = calculate_score("219", _central_generic_subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["average_grade"] == pytest.approx(1.0)
    assert result["used_subjects"] == 10


@_skip_no_db
def test_calculate_score_sangji_treats_korean_history_as_social_slot() -> None:
    subjects = [
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "통합사회", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "9"},
    ]

    result = calculate_score("219", subjects, {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(205.65)
    assert result["used_subjects"] == 10


@_skip_no_db
def test_calculate_score_sangji_holistic_tracks_are_noncalc() -> None:
    for uid in ("225", "226"):
        result = calculate_score(uid, _subjects(), {}, {})

        assert result["status"] == "non_calculation_track"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "SANGJI_2027_NON_CALCULATION_TRACK"
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
