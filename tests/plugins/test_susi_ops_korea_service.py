from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _korea_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1", "성취도": "E", "과목구분": "공통"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": "1", "성취도": "E", "과목구분": "공통"},
        {"학년": 1, "학기": 2, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1", "성취도": "E", "과목구분": "공통"},
        {"학년": 2, "학기": 1, "교과": "사회", "과목": "사회", "이수단위": 3, "등급": "1", "성취도": "E", "과목구분": "일반선택"},
        {"학년": 2, "학기": 2, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": "1", "성취도": "E", "과목구분": "일반선택"},
    ]


@_skip_no_db
def test_calculate_score_korea_general_uses_official_formula_plugin() -> None:
    result = calculate_score("92", _korea_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KOREA_SEJONG_2027_STUDENT_RECORD1000_GENERAL"
    assert result["student_record_score"] == pytest.approx(1000.0)


@_skip_no_db
def test_calculate_score_korea_qualitative_tracks_are_not_auto_calculated() -> None:
    result = calculate_score("93", _korea_subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KOREA_SEJONG_2027_NON_CALCULATION_TRACK"
