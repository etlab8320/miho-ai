from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1", "과목구분": "일반"},
    ]


@_skip_no_db
def test_calculate_score_jeonbuk_opportunity_is_non_calculation() -> None:
    result = calculate_score("331", _subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "JEONBUK_2027_STUDENT_RECORD_COMPREHENSIVE_DOCUMENT_NON_NUMERIC"
    assert result["stage_weights"]["stage2_other"] == "100"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "미적용"}
