from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows = [
        {"학년": 1 + index // 5, "학기": 1 + index % 2, "교과": "국어", "과목": f"국어{index}", "이수단위": 3, "등급": "1"}
        for index in range(10)
    ]
    rows.append({"학년": 3, "학기": 2, "교과": "국어", "과목": "졸업예정제외", "이수단위": 3, "등급": "1"})
    return rows


@_skip_no_db
def test_calculate_score_baejae_course_tracks_use_official_plugin() -> None:
    for uid in ("194", "195", "196", "197"):
        result = calculate_score(uid, _subjects(), {}, {})
        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "BAEJAE_2027_COURSE_BEST10"
        assert result["student_record_score"] == pytest.approx(1000.0)
        assert result["used_subjects"] == 10
        assert result["minimum_csat"]["has_minimum"] is False
