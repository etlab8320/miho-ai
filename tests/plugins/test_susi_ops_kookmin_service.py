from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


@_skip_no_db
def test_calculate_score_kookmin_frontier_stays_non_calculation_without_plugin_key() -> None:
    result = calculate_score(
        "104",
        [{"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"}],
        {"unexcused_absence_days": 7},
        {},
    )

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "non_calculation_rule"
    assert result["stage_weights"]["stage1_multiplier"] == "3"
    assert result["stage_weights"]["stage2_interview"] == "30"
