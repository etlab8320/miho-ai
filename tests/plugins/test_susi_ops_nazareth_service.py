from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    subjects: list[dict[str, object]] = []
    for grade in [1, 2, 3]:
        semesters = [1, 2] if grade < 3 else [1]
        for semester in semesters:
            for category in ["국어", "영어", "수학"]:
                subjects.append(
                    {
                        "학년": grade,
                        "학기": semester,
                        "교과": category,
                        "과목": f"{category}{grade}-{semester}",
                        "이수단위": 3,
                        "등급": "1",
                    }
                )
    return subjects


def _subjects_with_graduate_third_second() -> list[dict[str, object]]:
    subjects = _subjects()
    for category in ["국어", "영어", "수학"]:
        subjects.append(
            {
                "학년": 3,
                "학기": 2,
                "교과": category,
                "과목": f"{category}3-2",
                "이수단위": 3,
                "등급": "9",
            }
        )
    return subjects


@_skip_no_db
def test_calculate_score_nazareth_rehab_sports_uses_official_formula_plugin() -> None:
    result = calculate_score("108", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "NAZARETH_2027_OFFICIAL_REHAB_SPORTS_RECORD100_PRACTICAL900"
    assert result["student_record_score"] == pytest.approx(100.0)
    assert result["used_subjects"] == 15
    assert result["total_units"] == pytest.approx(45.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_nazareth_graduate_includes_third_grade_second_semester() -> None:
    result = calculate_score(
        "108",
        _subjects_with_graduate_third_second(),
        {"is_graduate": True},
        {},
    )

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(96.0)
    assert result["used_subjects"] == 18


@_skip_no_db
def test_calculate_score_nazareth_taekwondo_uses_interview_practical_formula() -> None:
    result = calculate_score("453", [], {"interview_score": 280, "practical_score": 650}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "NAZARETH_2027_TAEKWONDO_INTERVIEW300_PRACTICAL700"
    assert result["used_subjects"] == 0
    assert result["student_record_score"] == pytest.approx(280.0)
    assert result["record_full_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(930.0)
    assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_nazareth_taekwondo_special_tracks_are_registered() -> None:
    rural = calculate_score("454", [], {}, {})
    need_based = calculate_score("455", [], {}, {})

    for result in (rural, need_based):
        assert result["status"] == "calculated"
        assert result["formula_key"] == "NAZARETH_2027_TAEKWONDO_INTERVIEW300_PRACTICAL700"
        assert result["full_practical_total"] == pytest.approx(1000.0)
