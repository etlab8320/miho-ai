from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "영어", "과목": "영어1", "이수단위": 3, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "수학", "과목": "수학1", "이수단위": 3, "등급": "1"},
        {"학년": 2, "학기": 2, "교과": "사회", "과목": "사회1", "이수단위": 3, "등급": "1"},
        {"학년": 3, "학기": 1, "교과": "과학", "과목": "과학1", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사1", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "국어", "과목": "국어진로A", "이수단위": 3, "성취도": "A", "과목구분": "진로선택"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "영어진로A2", "이수단위": 3, "성취도": "A", "과목구분": "진로선택"},
    ]


@_skip_no_db
def test_calculate_score_dongmyeong_tracks_use_official_plugin() -> None:
    record = calculate_score("157", _subjects(), {}, {})
    practical = calculate_score("159", _subjects(), {}, {})
    interview = calculate_score("160", _subjects(), {"interview_score": 180}, {})
    creative = calculate_score("161", _subjects(), {}, {})

    assert record["strategy"] == "official_formula_plugin"
    assert record["student_record_score"] == pytest.approx(1000.0)
    assert practical["strategy"] == "official_formula_plugin"
    assert practical["student_record_score"] == pytest.approx(400.0)
    assert practical["vs_prev_year"]["practical_max"] == pytest.approx(600.0)
    assert interview["strategy"] == "official_formula_plugin"
    assert interview["student_record_score"] == pytest.approx(800.0)
    assert interview["full_practical_total"] == pytest.approx(980.0)
    assert creative["status"] == "non_calculation_track"
    assert creative["formula_key"] == "DONGMYEONG_2027_CREATIVE_HOLISTIC_NON_CALC"
