from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _perfect_kiu_subjects() -> list[dict[str, object]]:
    subjects: list[dict[str, object]] = []
    areas = ["국어", "영어", "수학", "사회", "과학"]
    for index in range(9):
        subjects.append(
            {
                "학년": 1 + index // 3,
                "학기": 1,
                "교과": areas[index % len(areas)],
                "과목": f"일반{index + 1}",
                "이수단위": 3,
                "등급": "1",
                "과목구분": "일반선택",
            }
        )
    for index in range(3):
        subjects.append(
            {
                "학년": 2,
                "학기": 1,
                "교과": areas[index],
                "과목": f"진로{index + 1}",
                "이수단위": 2,
                "성취도": "A",
                "과목구분": "진로선택",
            }
        )
    return subjects


@_skip_no_db
def test_calculate_score_kiu_general_uses_official_formula_plugin() -> None:
    result = calculate_score("47", _perfect_kiu_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KIU_2027_RECORD360_ATTENDANCE40"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["used_subjects"] == 12
    assert result["total_units"] == pytest.approx(33.0)


@_skip_no_db
def test_calculate_score_kiu_practical_keeps_record_attendance_and_practical_separate() -> None:
    result = calculate_score(
        "44",
        _perfect_kiu_subjects(),
        {"unexcused_absence_days": 4, "unexcused_late": 12},
        {},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KIU_2027_RECORD108_ATTENDANCE12_PRACTICAL280"
    assert result["student_record_score"] == pytest.approx(118.8)
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(280.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(398.8)


@_skip_no_db
def test_calculate_score_kiu_student_comprehensive_stays_non_calculation() -> None:
    result = calculate_score("45", _perfect_kiu_subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KIU_2027_NON_CALCULATION_STUDENT_RECORD_COMPREHENSIVE"
