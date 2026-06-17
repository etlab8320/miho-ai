from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in ["국어", "영어", "수학", "사회"]:
        rows.append({"학년": 1, "학기": 1, "교과": group, "과목": f"{group}1", "이수단위": 1, "등급": "1", "과목구분": "일반"})
        rows.append({"학년": 1, "학기": 2, "교과": group, "과목": f"{group}2", "이수단위": 1, "등급": "1", "과목구분": "일반"})
    rows.append({"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 1, "성취도": "A", "과목구분": "진로"})
    rows.append({"학년": 2, "학기": 2, "교과": "영어", "과목": "진로영어", "이수단위": 1, "성취도": "A", "과목구분": "진로"})
    return rows


@_skip_no_db
def test_calculate_score_hanseo_leisure_uses_official_formula_plugin() -> None:
    result = calculate_score("385", _subjects(), {"unexcused_absence_days": 7}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "HANSEO_2027_LEISURE_RECORD100_PRACTICAL900"
    assert result["student_record_score"] == pytest.approx(99.4)
    assert result["record_full_score"] == pytest.approx(100.0)
    assert result["practical_full_score"] == pytest.approx(900.0)
    assert result["full_practical_total"] == pytest.approx(999.4)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_hanseo_security_stays_non_calculation() -> None:
    result = calculate_score("384", _subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "HANSEO_2027_SECURITY_PRACTICAL_BASED_RECORD_HELD"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
