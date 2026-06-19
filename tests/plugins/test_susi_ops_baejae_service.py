from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows = [
        {"학년": 1 + index // 5, "학기": 1 + index % 2, "교과": "국어", "과목": f"국어{index}", "이수단위": 3, "등급": "1"}
        for index in range(10)
    ]
    rows.append({"학년": 3, "학기": 2, "교과": "국어", "과목": "졸업예정제외", "이수단위": 3, "등급": "1"})
    return rows


def _split_group_subjects(core_grade: str = "1", second_grade: str = "1", school_grade: int = 1) -> list[dict[str, object]]:
    rows = [
        {"학년": school_grade, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 1, "등급": core_grade},
        {"학년": school_grade, "학기": 1, "교과": "국어", "과목": "국어2", "이수단위": 1, "등급": core_grade},
        {"학년": school_grade, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 1, "등급": core_grade},
        {"학년": school_grade, "학기": 1, "교과": "영어", "과목": "영어2", "이수단위": 1, "등급": core_grade},
        {"학년": school_grade, "학기": 1, "교과": "수학", "과목": "수학1", "이수단위": 1, "등급": core_grade},
    ]
    rows.extend(
        [
            {"학년": school_grade, "학기": 1, "교과": "사회", "과목": "사회1", "이수단위": 1, "등급": second_grade},
            {"학년": school_grade, "학기": 1, "교과": "사회", "과목": "사회2", "이수단위": 1, "등급": second_grade},
            {"학년": school_grade, "학기": 1, "교과": "과학", "과목": "과학1", "이수단위": 1, "등급": second_grade},
            {"학년": school_grade, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 1, "등급": second_grade},
            {"학년": school_grade, "학기": 1, "교과": "한문", "과목": "한문", "이수단위": 1, "등급": second_grade},
        ]
    )
    return rows


@_skip_no_db
def test_calculate_score_baejae_course_tracks_use_official_plugin() -> None:
    for uid in ("194", "195", "196", "197"):
        result = calculate_score(uid, _split_group_subjects(), {}, {})
        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "BAEJAE_2027_COURSE_BEST10"
        assert result["student_record_score"] == pytest.approx(1000.0)
        assert result["used_subjects"] == 10
        assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_baejae_forces_five_subjects_from_each_group() -> None:
    subjects = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": f"국어{index}", "이수단위": 1, "등급": "1"}
        for index in range(10)
    ]
    subjects.extend(
        {"학년": 1, "학기": 1, "교과": "사회", "과목": f"사회{index}", "이수단위": 1, "등급": "9"}
        for index in range(5)
    )

    result = calculate_score("195", subjects, {}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(800.0)
    assert result["used_subjects"] == 10


@_skip_no_db
def test_calculate_score_baejae_applies_second_grade_subject_bonus() -> None:
    first_grade = calculate_score("195", _split_group_subjects("2", "2", school_grade=1), {}, {})
    second_grade = calculate_score("195", _split_group_subjects("2", "2", school_grade=2), {}, {})

    assert first_grade["student_record_score"] == pytest.approx(970.0)
    assert second_grade["student_record_score"] == pytest.approx(990.0)
