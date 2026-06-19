from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 4, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "국어", "과목": "국어2", "이수단위": 4, "등급": "2"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 4, "등급": "1"},
        {"학년": 2, "학기": 2, "교과": "영어", "과목": "영어2", "이수단위": 4, "등급": "3"},
    ]


@_skip_no_db
def test_calculate_score_gachon_main_practical_row_uses_official_plugin_key_from_self_check() -> None:
    result = calculate_score("1", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "GACHON_2027_PE_PRACTICAL_RECORD30_PRACTICAL70"
    assert result["record_full_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)


@_skip_no_db
def test_calculate_score_gachon_taekwondo_practical_row_uses_official_split() -> None:
    result = calculate_score("452", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == "GACHON_2027_PE_PRACTICAL_RECORD30_PRACTICAL70"
    assert result["average_grade"] == pytest.approx(1.75)
    assert result["student_record_score"] == pytest.approx(298.875)
    assert result["record_full_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(998.875)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
