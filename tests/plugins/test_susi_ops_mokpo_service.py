from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "통합사회", "이수단위": 3, "등급": "1"},
        {"학년": 3, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 1, "성취도": "A", "과목구분": "진로선택"},
        {"학년": 3, "학기": 1, "교과": "영어", "과목": "진로영어", "이수단위": 1, "성취도": "A", "과목구분": "진로선택"},
        {"학년": 3, "학기": 1, "교과": "사회", "과목": "사회문제탐구", "이수단위": 1, "성취도": "A", "과목구분": "진로선택"},
    ]


@_skip_no_db
def test_calculate_score_mokpo_course_tracks_use_official_plugin() -> None:
    general = calculate_score("185", _subjects(), {"unexcused_absence_days": 0}, {})
    regional = calculate_score("190", _subjects(), {"unexcused_absence_days": 0}, {})

    for result in (general, regional):
        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "MOKPO_2027_COURSE900_ATT100_CAREER_ADD5"
        assert result["student_record_score"] == pytest.approx(1005.0)
        assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_mokpo_holistic_and_zero_quota_are_official_noncalc() -> None:
    for uid in ("186", "187"):
        result = calculate_score(uid, _subjects(), {"unexcused_absence_days": 0}, {})
        assert result["status"] == "non_calculation_track"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "MOKPO_2027_NO_RECRUIT_OR_HOLISTIC"
        assert result["minimum_csat"]["has_minimum"] is False
