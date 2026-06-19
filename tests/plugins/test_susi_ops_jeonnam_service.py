from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path


_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 2, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "영어", "과목": "영어1", "이수단위": 2, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "수학", "과목": "수학1", "이수단위": 2, "등급": "1"},
        {"학년": 2, "학기": 2, "교과": "한국사", "과목": "한국사1", "이수단위": 2, "등급": "1"},
        {"학년": 3, "학기": 1, "교과": "사회", "과목": "사회미반영", "이수단위": 2, "등급": "9"},
        {"학년": 3, "학기": 1, "교과": "과학", "과목": "과학미반영", "이수단위": 2, "등급": "9"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "진로영어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        {"학년": 3, "학기": 1, "교과": "수학", "과목": "진로수학", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
    ]


@_skip_no_db
def test_calculate_score_jeonnam_pe_education_uses_official_subject_groups() -> None:
    result = calculate_score("317", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "JEONNAM_2027_PE_EDU_RECORD800_PRACTICAL200"
    assert result["student_record_score"] == pytest.approx(800.0)
    assert result["used_subjects"] == 7
    assert result["subject_flags"] == {
        "과학": "X",
        "국어": "O",
        "기타": "X",
        "사회": "X",
        "수학": "O",
        "영어": "O",
        "한국사": "O",
    }
