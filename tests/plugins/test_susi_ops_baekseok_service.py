from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    groups = ["국어", "수학", "영어", "사회", "한국사", "과학"]
    rows = [
        {"학년": 1 + index // 6, "학기": 1 if index >= 12 else 1 + index % 2, "교과": groups[index % len(groups)], "과목": f"일반{index}", "이수단위": 2, "등급": "1"}
        for index in range(15)
    ]
    rows.extend(
        [
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로A1", "이수단위": 1, "성취도": "A", "과목구분": "진로선택", "achievement_a_ratio": 0},
            {"학년": 2, "학기": 2, "교과": "영어", "과목": "진로A2", "이수단위": 1, "성취도": "A", "과목구분": "진로선택", "achievement_a_ratio": 0},
            {"학년": 3, "학기": 1, "교과": "과학", "과목": "진로A3", "이수단위": 1, "성취도": "A", "과목구분": "진로선택", "achievement_a_ratio": 0},
        ]
    )
    return rows


def _regular_grade_one_subjects() -> list[dict[str, object]]:
    groups = ["국어", "수학", "영어", "사회", "한국사", "과학"]
    return [
        {"학년": 1 + index // 6, "학기": 1 if index >= 12 else 1 + index % 2, "교과": groups[index % len(groups)], "과목": f"일반{index}", "이수단위": 2, "등급": "1"}
        for index in range(15)
    ]


@_skip_no_db
def test_calculate_score_baekseok_practical_tracks_use_official_plugin() -> None:
    sports = calculate_score("188", _subjects(), {"unexcused_absence_days": 0}, {})
    special = calculate_score("192", _subjects(), {"unexcused_absence_days": 0}, {})

    assert sports["status"] == "calculated"
    assert sports["strategy"] == "official_formula_plugin"
    assert sports["formula_key"] == "BAEKSEOK_2027_OFFICIAL_RECORD_PRACTICAL"
    assert sports["student_record_score"] == pytest.approx(400.0)
    assert sports["used_subjects"] == 18
    assert sports["vs_prev_year"]["practical_max"] == pytest.approx(600.0)
    assert sports["minimum_csat"]["has_minimum"] is False

    assert special["strategy"] == "official_formula_plugin"
    assert special["student_record_score"] == pytest.approx(600.0)
    assert special["used_subjects"] == 18
    assert special["vs_prev_year"]["practical_max"] == pytest.approx(400.0)


@_skip_no_db
def test_calculate_score_baekseok_career_subjects_use_all_subject_groups() -> None:
    grades = _regular_grade_one_subjects()
    grades.extend(
        [
            {"학년": 2, "학기": 1, "교과": "체육", "과목": "스포츠 생활", "이수단위": 1, "성취도": "A", "과목구분": "진로선택", "achievement_a_ratio": 0},
            {"학년": 2, "학기": 2, "교과": "예술", "과목": "음악 감상과 비평", "이수단위": 1, "성취도": "A", "과목구분": "진로선택", "achievement_a_ratio": 0},
            {"학년": 3, "학기": 1, "교과": "기술·가정", "과목": "정보과학", "이수단위": 1, "성취도": "A", "과목구분": "진로선택", "achievement_a_ratio": 0},
        ]
    )

    result = calculate_score("188", grades, {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["used_subjects"] == 18


@_skip_no_db
def test_calculate_score_baekseok_ignores_career_subjects_without_student_ratio() -> None:
    grades = _regular_grade_one_subjects()
    grades.extend(
        [
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로A", "이수단위": 1, "성취도": "A", "과목구분": "진로선택"},
            {"학년": 2, "학기": 2, "교과": "영어", "과목": "진로B", "이수단위": 1, "성취도": "B", "과목구분": "진로선택"},
            {"학년": 3, "학기": 1, "교과": "과학", "과목": "진로C", "이수단위": 1, "성취도": "C", "과목구분": "진로선택"},
        ]
    )

    result = calculate_score("188", grades, {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(380.0)
    assert result["used_subjects"] == 18


@_skip_no_db
def test_calculate_score_baekseok_school_violence_measures_are_summed() -> None:
    result = calculate_score("188", _subjects(), {"school_violence_measures": [4, 9]}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["full_practical_total"] == pytest.approx(986.0)


@_skip_no_db
def test_calculate_score_baekseok_creative_tracks_are_official_noncalc() -> None:
    for uid in ("198", "200"):
        result = calculate_score(uid, _subjects(), {}, {})
        assert result["status"] == "non_calculation_track"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "BAEKSEOK_2027_CREATIVE_TALENT_NON_CALCULATION"
        assert result["minimum_csat"]["has_minimum"] is False
