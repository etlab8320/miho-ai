from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "DEU_2027_OFFICIAL_SILGI_TOP12_RECORD_PRACTICAL"


def _subjects_with_three_careers() -> list[dict[str, object]]:
    rows = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": f"일반{i}", "이수단위": 3, "등급": "1", "과목구분": "일반"}
        for i in range(9)
    ]
    rows.append({"학년": 2, "학기": 1, "교과": "영어", "과목": "일반저점", "이수단위": 3, "등급": "9", "과목구분": "일반"})
    rows.extend(
        {"학년": 2, "학기": 1, "교과": "사회", "과목": f"진로{i}", "이수단위": 3, "성취도": "A", "과목구분": "진로"}
        for i in range(3)
    )
    return rows


def _perfect_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1 + index % 2, "교과": "국어", "과목": f"일반{index}", "이수단위": 3, "등급": "1", "과목구분": "일반"}
        for index in range(12)
    ]


def _single_subject() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1", "과목구분": "일반"}
    ]


@_skip_no_db
def test_calculate_score_deu_career_subjects_are_limited_to_two() -> None:
    result = calculate_score("177", _subjects_with_three_careers(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(275.0)
    assert result["full_practical_total"] == pytest.approx(975.0)


@_skip_no_db
def test_calculate_score_deu_taekwondo_silgi_track_is_registered() -> None:
    result = calculate_score("463", _perfect_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["record_full_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)


@_skip_no_db
def test_calculate_score_deu_short_subject_pool_does_not_add_fake_grade9_subjects() -> None:
    result = calculate_score("177", _single_subject(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(25.0)
    assert result["average_grade"] == pytest.approx(1.0)
    assert result["used_subjects"] == 1
