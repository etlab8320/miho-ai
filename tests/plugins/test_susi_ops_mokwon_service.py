from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, group in enumerate(["국어", "영어", "수학", "사회", "과학"]):
        rows.append({"학년": 1, "학기": 1, "교과": group, "과목": f"{group}{index}", "이수단위": 3, "등급": "1"})
    for index in range(3):
        rows.append({"학년": 2, "학기": 1, "교과": "국어", "과목": f"진로{index}", "이수단위": 3, "성취도": "A", "과목구분": "진로선택"})
    return rows


@_skip_no_db
def test_calculate_score_mokwon_tracks_use_official_plugin() -> None:
    practical = calculate_score("182", _subjects(), {}, {})
    course = calculate_score("183", _subjects(), {}, {})
    regional = calculate_score("184", _subjects(), {}, {})

    assert practical["status"] == "calculated"
    assert practical["strategy"] == "official_formula_plugin"
    assert practical["formula_key"] == "MOKWON_2027_OFFICIAL_TOP5_CAREER3_DENOM785"
    assert practical["student_record_score"] == pytest.approx(100.0)
    assert practical["used_subjects"] == 8
    assert practical["minimum_csat"]["has_minimum"] is False
    assert practical["vs_prev_year"]["practical_max"] == pytest.approx(900.0)

    assert course["strategy"] == "official_formula_plugin"
    assert course["student_record_score"] == pytest.approx(1000.0)
    assert regional["strategy"] == "official_formula_plugin"
    assert regional["student_record_score"] == pytest.approx(1000.0)
