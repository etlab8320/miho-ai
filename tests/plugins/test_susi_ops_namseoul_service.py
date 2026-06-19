from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _perfect_subjects() -> list[dict[str, object]]:
    subjects: list[dict[str, object]] = []
    placements = [
        (1, 1, "국어"),
        (1, 2, "영어"),
        (2, 1, "수학"),
        (2, 2, "사회"),
        (3, 1, "과학"),
        (1, 1, "한국사"),
        (1, 2, "국어"),
        (2, 1, "영어"),
        (2, 2, "수학"),
        (3, 1, "사회"),
        (3, 1, "과학"),
        (2, 2, "한국사"),
    ]
    for index, (grade, semester, category) in enumerate(placements):
        subjects.append(
            {
                "학년": grade,
                "학기": semester,
                "교과": category,
                "과목": f"{category}{index + 1}",
                "이수단위": 3,
                "등급": "1",
            }
        )
    for index, category in enumerate(["국어", "영어", "수학"]):
        subjects.append(
            {
                "학년": 3,
                "학기": 1,
                "교과": category,
                "과목": f"진로{index + 1}",
                "이수단위": 1,
                "등급": "",
                "성취도": "A",
            }
        )
    return subjects


@_skip_no_db
def test_calculate_score_namseoul_practical_includes_700_practical_full_score() -> None:
    result = calculate_score("109", _perfect_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "NAMSEOUL_2027_TOP12_REGULAR_TOP3_CAREER"
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(700.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_namseoul_comprehensive_interview_is_non_calculation_with_no_minimum() -> None:
    result = calculate_score("113", _perfect_subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["formula_key"] == "NAMSEOUL_2027_NON_CALCULATION_TRACK"
    assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_namseoul_regional_uses_top_two_practical_events() -> None:
    result = calculate_score(
        "114",
        _perfect_subjects(),
        {"practical_event_scores": [80, 90, 50]},
        {},
    )

    assert result["status"] == "calculated"
    assert result["formula_key"] == "NAMSEOUL_2027_TOP12_REGULAR_TOP3_CAREER"
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(895.0)


@_skip_no_db
def test_calculate_score_namseoul_school_violence_follows_pdf_table() -> None:
    deducted = calculate_score("111", _perfect_subjects(), {"school_violence_measures": [1, 4, 6]}, {})
    ineligible = calculate_score("111", _perfect_subjects(), {"school_violence_measure": 8}, {})

    assert deducted["status"] == "calculated"
    assert deducted["full_practical_total"] == pytest.approx(940.0)
    assert ineligible["status"] == "namseoul_school_violence_ineligible"
    assert ineligible["formula_key"] == "NAMSEOUL_2027_SCHOOL_VIOLENCE_INELIGIBLE"
