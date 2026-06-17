from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

HALLYM_KEY = "HALLYM_2027_OFFICIAL_COURSE900_ATTENDANCE100"
HALLYM_NON_CALC_KEY = "HALLYM_2027_STUDENT_COMPREHENSIVE_NON_CALCULATION"
KMOU_KEY = "KMOU_2027_OFFICIAL_ARTSPORT_RECORD600_PRACTICAL400"
KMOU_MINIMUM = "해양과학기술대학: 수학, 영어, 탐구(사회·과학) 중 1개 영역 이상 5등급 이내"


def _hallym_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 3, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 3, "등급": "1"},
        {"학년": 3, "학기": 1, "교과": "수학", "과목": "수학1", "이수단위": 3, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 1, "성취도": "A"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "진로영어", "이수단위": 1, "성취도": "A"},
        {"학년": 3, "학기": 1, "교과": "수학", "과목": "진로수학", "이수단위": 1, "성취도": "A"},
    ]


def _kmou_subjects(rank: str = "1") -> list[dict[str, object]]:
    rows = []
    for group in ["국어", "영어", "수학", "사회", "한국사"]:
        rows.append({"학년": 1, "학기": 1, "교과": group, "과목": f"{group}1", "이수단위": 3, "등급": rank})
        rows.append({"학년": 2, "학기": 1, "교과": group, "과목": f"{group}2", "이수단위": 3, "등급": rank})
    rows.extend(
        [
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "심화국어", "이수단위": 2, "성취도": "A"},
            {"학년": 2, "학기": 1, "교과": "영어", "과목": "영어권문화", "이수단위": 2, "성취도": "A"},
            {"학년": 3, "학기": 1, "교과": "수학", "과목": "기하", "이수단위": 2, "성취도": "A"},
        ]
    )
    return rows


@_skip_no_db
def test_calculate_score_hallym_course_tracks_use_official_formula() -> None:
    for uid in ["377", "378", "386", "388"]:
        result = calculate_score(uid, _hallym_subjects(), {}, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == HALLYM_KEY
        assert result["student_record_score"] == pytest.approx(1000.0)
        assert result["record_full_score"] == pytest.approx(1000.0)
        assert result["practical_full_score"] == pytest.approx(0.0)
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_hallym_non_calculation_track_uses_official_key() -> None:
    result = calculate_score("387", _hallym_subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == HALLYM_NON_CALC_KEY
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_kmou_tracks_use_official_formula_and_minimum() -> None:
    for uid in ["379", "380", "381", "382"]:
        result = calculate_score(uid, _kmou_subjects(), {}, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == KMOU_KEY
        assert result["student_record_score"] == pytest.approx(600.0)
        assert result["record_full_score"] == pytest.approx(600.0)
        assert result["practical_full_score"] == pytest.approx(400.0)
        assert result["full_practical_total"] == pytest.approx(1000.0)
        assert result["minimum_csat"] == {"has_minimum": True, "detail": KMOU_MINIMUM}
