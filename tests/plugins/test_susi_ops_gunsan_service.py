from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


@_skip_no_db
def test_calculate_score_gunsan_physical_education_general_is_non_calculation() -> None:
    result = calculate_score("110", [{"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "등급": "1"}], {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "non_calculation_rule"
    assert result["minimum_csat"]["has_minimum"] is False
