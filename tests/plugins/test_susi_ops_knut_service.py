from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "KNUT_2027_OFFICIAL_RECORD_PRACTICAL_TOP_SUBJECTS"


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    rows = []
    for group in ["국어", "영어", "수학", "사회"]:
        for number in range(3):
            rows.append(
                {
                    "학년": 1 + number // 2,
                    "학기": 1 + number % 2,
                    "교과": group,
                    "과목": f"{group}{number + 1}",
                    "이수단위": 5,
                    "등급": rank,
                }
            )
    rows.extend(
        [
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "심화국어", "이수단위": 5, "성취도": "A", "과목구분": "진로"},
            {"학년": 2, "학기": 2, "교과": "영어", "과목": "영어권문화", "이수단위": 5, "성취도": "A", "과목구분": "진로"},
            {"학년": 3, "학기": 1, "교과": "사회", "과목": "사회문제탐구", "이수단위": 5, "성취도": "A", "과목구분": "진로"},
        ]
    )
    return rows


def _semester_subjects() -> list[dict[str, object]]:
    rows = []
    for group in ["국어", "영어", "수학", "사회"]:
        rows.extend(
            [
                {"학년": 1, "학기": 1, "교과": group, "과목": f"{group}1", "이수단위": 5, "등급": "1"},
                {"학년": 2, "학기": 1, "교과": group, "과목": f"{group}2", "이수단위": 5, "등급": "1"},
                {"학년": 3, "학기": 2, "교과": group, "과목": f"{group}졸업반영", "이수단위": 5, "등급": "9"},
            ]
        )
    return rows


@_skip_no_db
def test_calculate_score_knut_record_practical_components() -> None:
    industry = calculate_score("339", _subjects(), {}, {})
    medicine = calculate_score("341", _subjects(), {}, {})

    assert industry["status"] == "calculated"
    assert industry["formula_key"] == FORMULA_KEY
    assert industry["student_record_score"] == pytest.approx(300.0)
    assert industry["record_full_score"] == pytest.approx(300.0)
    assert industry["practical_full_score"] == pytest.approx(700.0)
    assert industry["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
    assert medicine["student_record_score"] == pytest.approx(600.0)
    assert medicine["record_full_score"] == pytest.approx(600.0)
    assert medicine["practical_full_score"] == pytest.approx(400.0)


@_skip_no_db
def test_calculate_score_knut_semester_context_and_absent() -> None:
    current = calculate_score("339", _semester_subjects(), {}, {})
    graduate = calculate_score("339", _semester_subjects(), {}, {}, {"is_graduate": True})
    absent = calculate_score("339", _subjects(), {"practical_absent": True}, {})

    assert current["status"] == "calculated"
    assert current["student_record_score"] == pytest.approx(300.0)
    assert graduate["student_record_score"] == pytest.approx(260.0)
    assert absent["status"] == "knut_practical_absent_ineligible"
    assert absent["formula_key"] == FORMULA_KEY
