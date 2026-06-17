from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    groups = ["국어", "영어", "수학", "사회", "한국사", "과학"]
    rows = [
        {
            "학년": 1 + index // 6,
            "학기": 1 if index >= 12 else 1 + index % 2,
            "교과": groups[index % len(groups)],
            "과목": f"일반{index}",
            "이수단위": 5,
            "등급": "1",
        }
        for index in range(12)
    ]
    rows.extend(
        [
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로A1", "이수단위": 5, "성취도": "A", "과목구분": "진로선택"},
            {"학년": 2, "학기": 2, "교과": "영어", "과목": "진로A2", "이수단위": 5, "성취도": "A", "과목구분": "진로선택"},
            {"학년": 3, "학기": 1, "교과": "수학", "과목": "진로A3", "이수단위": 5, "성취도": "A", "과목구분": "진로선택"},
        ]
    )
    return rows


@_skip_no_db
def test_calculate_score_pknu_practical_uses_stage1_40_and_minimum_none() -> None:
    result = calculate_score("199", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "PKNU_2027_OFFICIAL_RECORD_ATTENDANCE_PRACTICAL"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["used_subjects"] == 15
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(600.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_pknu_course_track_exposes_minimum_csat() -> None:
    result = calculate_score("201", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": True, "detail": "2합 8"}


@_skip_no_db
def test_calculate_score_pknu_rural_track_has_no_minimum_csat() -> None:
    result = calculate_score("205", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_pknu_future_track_has_no_minimum_csat() -> None:
    result = calculate_score("207", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_pknu_social_consideration_is_noncalc() -> None:
    result = calculate_score("208", _subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "PKNU_2027_STUDENT_COMPREHENSIVE_NON_CALCULATION"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
