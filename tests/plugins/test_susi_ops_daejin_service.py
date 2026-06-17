from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    subjects: list[dict[str, object]] = []
    groups = ["국어", "영어", "수학", "사회", "한국사", "과학"]
    for index in range(18):
        subjects.append(
            {
                "학년": 1 + index // 8,
                "학기": 1 + index % 2,
                "교과": groups[index % len(groups)],
                "과목": f"과목{index}",
                "이수단위": 3,
                "등급": "1",
            }
        )
    subjects.append({"학년": 3, "학기": 2, "교과": "국어", "과목": "제외3-2", "이수단위": 3, "등급": "1"})
    return subjects


@_skip_no_db
def test_calculate_score_daejin_practical_track_uses_official_plugin() -> None:
    result = calculate_score("146", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "DAEJIN_2027_OFFICIAL_TOP18_RECORD_ONLY_OR_RECORD200_PRACTICAL800"
    assert result["student_record_score"] == pytest.approx(200.0)
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(800.0)
    assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_daejin_basic_and_rural_zero_quota() -> None:
    basic = calculate_score("145", _subjects(), {}, {})
    rural = calculate_score("150", _subjects(), {}, {})

    assert basic["status"] == "calculated"
    assert basic["strategy"] == "official_formula_plugin"
    assert basic["student_record_score"] == pytest.approx(1000.0)
    assert rural["status"] == "non_calculation_track"
    assert rural["formula_key"] == "DAEJIN_2027_NO_RECRUITMENT_ROW"
