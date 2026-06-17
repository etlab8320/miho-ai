from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "영어", "과목": "영어1", "이수단위": 1, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "수학", "과목": "수학1", "이수단위": 1, "등급": "1"},
        {"학년": 2, "학기": 2, "교과": "사회", "과목": "사회1", "이수단위": 1, "등급": "1"},
        {"학년": 3, "학기": 1, "교과": "과학", "과목": "과학1", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사1", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "제2외국어", "과목": "일본어1", "이수단위": 1, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로A1", "이수단위": 1, "성취도": "A", "과목구분": "진로선택"},
        {"학년": 2, "학기": 2, "교과": "영어", "과목": "진로A2", "이수단위": 1, "성취도": "A", "과목구분": "진로선택"},
        {"학년": 3, "학기": 1, "교과": "사회", "과목": "사회2", "이수단위": 1, "등급": "1"},
        {"학년": 3, "학기": 2, "교과": "국어", "과목": "반영제외", "이수단위": 1, "등급": "1"},
    ]
    return rows


@_skip_no_db
def test_calculate_score_bufs_practical_tracks_use_official_plugin() -> None:
    for uid in ("206", "209"):
        result = calculate_score(uid, _subjects(), {}, {})
        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "BUFS_2027_OFFICIAL_COURSE_INTERVIEW_PRACTICAL"
        assert result["student_record_score"] == pytest.approx(400.0)
        assert result["used_subjects"] == 10
        assert result["vs_prev_year"]["practical_max"] == pytest.approx(600.0)
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_bufs_interview_tracks_use_official_plugin() -> None:
    for uid in ("213", "216"):
        result = calculate_score(uid, _subjects(), {}, {})
        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "BUFS_2027_OFFICIAL_COURSE_INTERVIEW_PRACTICAL"
        assert result["student_record_score"] == pytest.approx(700.0)
        assert result["used_subjects"] == 10
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_bufs_student_document_tracks_are_noncalc() -> None:
    for uid in ("215", "218"):
        result = calculate_score(uid, _subjects(), {}, {})
        assert result["status"] == "non_calculation_track"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "BUFS_2027_STUDENT_DOCUMENT_NON_CALCULATION"
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
