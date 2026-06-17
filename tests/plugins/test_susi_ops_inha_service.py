from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1", "과목구분": "일반"},
    ]


@_skip_no_db
def test_calculate_score_inha_future_talent_interview_is_non_calculation() -> None:
    for uid in ("328", "330"):
        result = calculate_score(uid, _subjects(), {}, {})

        assert result["status"] == "non_calculation_track"
        assert result["strategy"] == "non_calculation_rule"
        assert result["stage_weights"]["stage1_multiplier"] == "3.5"
        assert result["stage_weights"]["stage1_student_record"] == "100"
        assert result["stage_weights"]["stage2_other"] == "70"
        assert result["stage_weights"]["stage2_interview"] == "30"
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "미적용"}


@_skip_no_db
def test_calculate_score_inha_rural_rows_are_non_calculation() -> None:
    for uid in ("327", "329"):
        result = calculate_score(uid, _subjects(), {}, {})

        assert result["status"] == "non_calculation_track"
        assert result["stage_weights"]["stage2_other"] == "100"
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "미적용"}
