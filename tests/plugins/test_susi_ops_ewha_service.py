from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

MINIMUM_DETAIL = "국어, 수학, 영어, 탐구(사회/과학) 4개 영역 중 3개 영역 등급 합 9 이내"


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1", "과목구분": "일반"},
    ]


@_skip_no_db
def test_calculate_score_ewha_arts_document_is_qualitative_non_calculation() -> None:
    result = calculate_score("318", _subjects(), {"unexcused_absence_days": 7}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "non_calculation_rule"
    assert result["stage_weights"]["stage1_multiplier"] == "4"
    assert result["stage_weights"]["stage1_other"] == "100"
    assert result["stage_weights"]["stage2_other"] == "80"
    assert result["stage_weights"]["stage2_interview"] == "20"
    assert result["minimum_csat"] == {"has_minimum": True, "detail": MINIMUM_DETAIL}
    assert result["attendance_seen"] is True
