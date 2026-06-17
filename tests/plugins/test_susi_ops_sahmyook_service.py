from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": "5"},
    ]


@_skip_no_db
def test_calculate_score_sahmyook_school_recommendation_uses_official_plugin() -> None:
    result = calculate_score("212", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SAHMYOOK_2027_SCHOOL_RECOMMENDATION_PE_TOP2_GROUPS"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["record_full_score"] == pytest.approx(400.0)
    assert result["practical_full_score"] == pytest.approx(600.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["used_subjects"] == 2
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(600.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_sahmyook_pastor_recommendation_is_noncalc() -> None:
    result = calculate_score("220", _subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SAHMYOOK_2027_PASTOR_RECOMMENDATION_PE_NON_CALCULATION"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
