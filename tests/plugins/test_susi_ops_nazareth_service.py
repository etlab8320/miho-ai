from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    subjects: list[dict[str, object]] = []
    for grade in [1, 2, 3]:
        semesters = [1, 2] if grade < 3 else [1]
        for semester in semesters:
            for category in ["국어", "영어", "수학"]:
                subjects.append(
                    {
                        "학년": grade,
                        "학기": semester,
                        "교과": category,
                        "과목": f"{category}{grade}-{semester}",
                        "이수단위": 3,
                        "등급": "1",
                    }
                )
    return subjects


@_skip_no_db
def test_calculate_score_nazareth_rehab_sports_uses_official_formula_plugin() -> None:
    result = calculate_score("108", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "NAZARETH_2027_OFFICIAL_REHAB_SPORTS_RECORD100_PRACTICAL900"
    assert result["student_record_score"] == pytest.approx(100.0)
    assert result["used_subjects"] == 15
    assert result["total_units"] == pytest.approx(45.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"]["has_minimum"] is False
