from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    subjects: list[dict[str, object]] = []
    for index, category in enumerate(["국어", "영어", "수학", "사회", "한국사", "과학", "국어", "영어"]):
        subjects.append(
            {
                "학년": 1 + index // 4,
                "학기": 1 + index % 2,
                "교과": category,
                "과목": f"{category}{index + 1}",
                "이수단위": 3,
                "등급": "1",
            }
        )
    subjects.extend(
        [
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로A", "이수단위": 1, "성취도": "A"},
            {"학년": 2, "학기": 2, "교과": "영어", "과목": "진로B", "이수단위": 1, "성취도": "B"},
        ]
    )
    return subjects


@_skip_no_db
def test_calculate_score_daegu_catholic_life_practical_uses_official_formula() -> None:
    result = calculate_score("121", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(200.0)
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(800.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_daegu_catholic_all_regular_grade_nine_zero_rule() -> None:
    subjects = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 1, "등급": "9"},
        {"학년": 1, "학기": 2, "교과": "영어", "과목": "영어", "이수단위": 1, "등급": "9"},
        {"학년": 2, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 1, "등급": "9"},
        {"학년": 2, "학기": 2, "교과": "사회", "과목": "사회", "이수단위": 1, "등급": "9"},
        {"학년": 3, "학기": 1, "교과": "과학", "과목": "과학", "이수단위": 1, "등급": "9"},
    ]

    result = calculate_score("121", subjects, {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(40.0)


@_skip_no_db
def test_calculate_score_daegu_catholic_pe_general_exposes_official_minimum_csat() -> None:
    result = calculate_score("123", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["minimum_csat"]["has_minimum"] is True
    assert "3개 영역 등급 합 5" in result["minimum_csat"]["detail"]
    assert "미적분 또는 기하" in result["minimum_csat"]["detail"]
    assert "과학탐구 2과목 평균" in result["minimum_csat"]["detail"]


@_skip_no_db
def test_calculate_score_daegu_catholic_pe_practical_exposes_minimum_csat() -> None:
    result = calculate_score("124", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["minimum_csat"]["has_minimum"] is True
    assert "2개 영역 등급 합 10" in result["minimum_csat"]["detail"]
