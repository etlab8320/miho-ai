from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _perfect_kyungwoon_subjects() -> list[dict[str, object]]:
    subjects: list[dict[str, object]] = []
    for area in ("국어", "영어", "수학"):
        for index in range(2):
            subjects.append(
                {
                    "학년": 1,
                    "학기": index + 1,
                    "교과": area,
                    "과목": f"{area}{index + 1}",
                    "이수단위": 3,
                    "등급": "1",
                }
            )
    for area in ("사회", "과학", "한국사"):
        subjects.append(
            {
                "학년": 2,
                "학기": 1,
                "교과": area,
                "과목": area,
                "이수단위": 3,
                "등급": "1",
            }
        )
    return subjects


def _core_career_subjects_over_limit() -> list[dict[str, object]]:
    subjects: list[dict[str, object]] = [
        {
            "학년": 1,
            "학기": 1,
            "교과": "국어",
            "과목": f"진로국어{index}",
            "이수단위": 3,
            "과목유형": "진로선택",
            "성취도": "A",
        }
        for index in range(6)
    ]
    subjects.extend(
        {
            "학년": 1,
            "학기": 1,
            "교과": "수학",
            "과목": f"일반수학{index}",
            "이수단위": 3,
            "등급": "9",
        }
        for index in range(3)
    )
    subjects.extend(
        {
            "학년": 2,
            "학기": 1,
            "교과": area,
            "과목": area,
            "이수단위": 3,
            "등급": "1",
        }
        for area in ("사회", "과학", "한국사")
    )
    return subjects


@_skip_no_db
@pytest.mark.parametrize("university_id", ["40", "42"])
def test_calculate_score_kyungwoon_course_tracks_use_official_formula(university_id: str) -> None:
    result = calculate_score(
        university_id=university_id,
        grades=_perfect_kyungwoon_subjects(),
        attendance={},
        practical_records={},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KYUNGWOON_2027_STUDENT_RECORD540_ATTENDANCE60"
    assert result["student_record_score"] == pytest.approx(600.0)
    assert result["used_subjects"] == 9
    assert result["total_units"] == pytest.approx(27.0)


@_skip_no_db
def test_calculate_score_kyungwoon_practical_keeps_record_and_practical_separate() -> None:
    result = calculate_score(
        university_id="41",
        grades=_perfect_kyungwoon_subjects(),
        attendance={},
        practical_records={},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KYUNGWOON_2027_PRACTICAL_RECORD162_ATTENDANCE18_PRACTICAL420"
    assert result["student_record_score"] == pytest.approx(180.0)
    assert result["used_subjects"] == 9
    assert result["total_units"] == pytest.approx(27.0)
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(420.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(600.0)


@_skip_no_db
def test_calculate_score_kyungwoon_attendance_uses_unexcused_absence_days_only() -> None:
    result = calculate_score(
        university_id="41",
        grades=_perfect_kyungwoon_subjects(),
        attendance={"unexcused_absence_days": 2, "unexcused_late": 9},
        practical_records={},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(179.4)
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(420.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(599.4)


@_skip_no_db
def test_calculate_score_kyungwoon_limits_career_subjects_by_group() -> None:
    result = calculate_score(
        university_id="40",
        grades=_core_career_subjects_over_limit(),
        attendance={},
        practical_records={},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(528.0)
    assert result["used_subjects"] == 9
