from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 2, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "국어", "과목": "국어2", "이수단위": 2, "등급": "2"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "국어3제외", "이수단위": 2, "등급": "5"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 2, "등급": "2"},
        {"학년": 1, "학기": 2, "교과": "영어", "과목": "영어2", "이수단위": 2, "등급": "3"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학1", "이수단위": 2, "등급": "4"},
        {"학년": 1, "학기": 2, "교과": "수학", "과목": "수학2", "이수단위": 2, "등급": "5"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사1", "이수단위": 2, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "사회", "과목": "사회1", "이수단위": 2, "등급": "6"},
        {"학년": 2, "학기": 1, "교과": "과학", "과목": "과학1제외", "이수단위": 2, "등급": "7"},
        {"학년": 2, "학기": 1, "교과": "사회", "과목": "진로제외", "이수단위": 2, "성취도": "A", "과목구분": "진로선택"},
        {"학년": 3, "학기": 2, "교과": "국어", "과목": "3-2반영", "이수단위": 2, "등급": "1"},
    ]


@_skip_no_db
def test_calculate_score_daejeon_practical_track_uses_official_plugin() -> None:
    result = calculate_score("141", _subjects(), {"unexcused_absence_days": 7, "unexcused_late": 1, "unexcused_early_leave": 3}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "DAEJEON_2027_SPORTS_PRACTICAL_RECORD40_PRACTICAL60"
    assert result["student_record_score"] == pytest.approx(379.25)
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(600.0)
    assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_daejeon_rural_and_hyehwa_tracks() -> None:
    rural = calculate_score("142", _subjects(), {"unexcused_absence_days": 7, "unexcused_late": 1, "unexcused_early_leave": 3}, {})
    hyehwa = calculate_score("144", _subjects(), {}, {})

    assert rural["status"] == "calculated"
    assert rural["strategy"] == "official_formula_plugin"
    assert rural["formula_key"] == "DAEJEON_2027_RURAL_GENERAL_RECORD100"
    assert rural["student_record_score"] == pytest.approx(975.25)
    assert hyehwa["status"] == "non_calculation_track"
    assert hyehwa["formula_key"] == "DAEJEON_2027_HYEHWA_DOCUMENT_NON_CALCULATION"
