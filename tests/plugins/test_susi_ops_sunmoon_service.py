from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    groups = ["국어", "영어", "수학", "사회", "과학", "한국사"]
    return [
        {
            "학년": 1 + index // 6,
            "학기": 1 + index % 2,
            "교과": groups[index % len(groups)],
            "과목": f"일반{index}",
            "이수단위": 3,
            "등급": "1",
            "과목구분": "일반",
        }
        for index in range(12)
    ]


@_skip_no_db
def test_calculate_score_sunmoon_uses_official_formula_plugin() -> None:
    result = calculate_score("246", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SUNMOON_2027_PRACTICAL_RECORD200_PRACTICAL800"
    assert result["student_record_score"] == pytest.approx(200.0)
    assert result["record_full_score"] == pytest.approx(200.0)
    assert result["practical_full_score"] == pytest.approx(800.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["used_subjects"] == 12
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_sunmoon_applies_highest_school_violence_deduction() -> None:
    result = calculate_score("247", _subjects(), {"school_violence_measures": [2, 5]}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SUNMOON_2027_PRACTICAL_RECORD200_PRACTICAL800"
    assert result["student_record_score"] == pytest.approx(200.0)
    assert result["full_practical_total"] == pytest.approx(932.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(932.0)
