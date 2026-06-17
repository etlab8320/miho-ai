from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "CHANGWON_2027_ATHLETICS_RECORD300_PRACTICAL700"


def _subjects() -> list[dict[str, object]]:
    subjects = [
        (1, 1, "국어", "국어1", 3, "1"),
        (1, 1, "영어", "영어1", 3, "1"),
        (1, 2, "수학", "수학1", 3, "1"),
        (1, 2, "사회", "통합사회", 3, "1"),
        (1, 2, "과학", "통합과학", 3, "1"),
        (1, 1, "한국사", "한국사", 3, "9"),
        (2, 1, "국어", "국어2", 3, "1"),
        (2, 1, "영어", "영어2", 3, "1"),
        (2, 2, "사회", "사회2", 3, "1"),
        (2, 2, "과학", "과학미반영", 3, "9"),
    ]
    rows = [
        {"학년": grade, "학기": semester, "교과": category, "과목": subject, "이수단위": credit, "등급": rank}
        for grade, semester, category, subject, credit, rank in subjects
    ]
    rows.extend(
        [
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
            {"학년": 2, "학기": 2, "교과": "영어", "과목": "진로영어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
            {"학년": 3, "학기": 1, "교과": "수학", "과목": "진로수학", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        ]
    )
    return rows


@_skip_no_db
def test_calculate_score_changwon_uses_official_plugin_and_subject_contract() -> None:
    result = calculate_score("337", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["used_subjects"] == 11
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["record_full_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["subject_flags"]["과학"] == "1학년만 O"
    assert result["subject_flags"]["한국사"] == "X"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_changwon_practical_event_absent_is_ineligible() -> None:
    result = calculate_score("337", _subjects(), {"practical_event_absent": True}, {})

    assert result["status"] == "changwon_practical_absent_ineligible"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
