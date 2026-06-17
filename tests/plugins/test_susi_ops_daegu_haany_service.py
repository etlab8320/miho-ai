from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 4, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학1", "이수단위": 5, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 3, "등급": "2"},
        {"학년": 1, "학기": 2, "교과": "사회", "과목": "사회1", "이수단위": 2, "등급": "3"},
        {"학년": 1, "학기": 2, "교과": "과학", "과목": "과학1", "이수단위": 4, "등급": "4"},
        {"학년": 1, "학기": 2, "교과": "한국사", "과목": "한국사1", "이수단위": 3, "등급": "5"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "국어2", "이수단위": 1, "등급": "2"},
        {"학년": 2, "학기": 1, "교과": "수학", "과목": "수학2", "이수단위": 2, "등급": "2"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "영어2", "이수단위": 3, "등급": "3"},
        {"학년": 2, "학기": 2, "교과": "사회", "과목": "사회2", "이수단위": 4, "등급": "4"},
        {"학년": 2, "학기": 2, "교과": "과학", "과목": "과학2", "이수단위": 5, "등급": "5"},
        {"학년": 3, "학기": 1, "교과": "국어", "과목": "국어3", "이수단위": 3, "등급": "6"},
        {"학년": 3, "학기": 1, "교과": "영어", "과목": "영어3", "이수단위": 3, "등급": "7"},
        {"학년": 3, "학기": 2, "교과": "국어", "과목": "제외3-2", "이수단위": 5, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "사회", "과목": "사회진로A", "이수단위": 5, "성취도": "A", "과목구분": "진로선택"},
        {"학년": 2, "학기": 2, "교과": "과학", "과목": "과학진로B", "이수단위": 1, "성취도": "B", "과목구분": "진로선택"},
        {"학년": 3, "학기": 1, "교과": "영어", "과목": "영어진로C", "이수단위": 4, "성취도": "C", "과목구분": "진로선택"},
        {"학년": 3, "학기": 1, "교과": "한국사", "과목": "한국사진로제외", "이수단위": 4, "성취도": "A", "과목구분": "진로선택"},
    ]


@_skip_no_db
def test_calculate_score_daegu_haany_general_track_uses_official_plugin() -> None:
    result = calculate_score("138", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "DAEGU_HAANY_2027_TOP9_REGULAR_CAREER3_OFFICIAL"
    assert result["student_record_score"] == pytest.approx(996.38)
    assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_daegu_haany_interview_track_uses_attendance_table() -> None:
    result = calculate_score("137", _subjects(), {"unexcused_absence_days": 7}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(743.83)
    assert result["stage_weights"]["stage2_interview"] == "25"
    assert result["attendance_seen"] is True


@_skip_no_db
def test_calculate_score_daegu_haany_practical_track_uses_900_practical() -> None:
    result = calculate_score("136", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(99.64)
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(900.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(999.64)
