from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    groups = ["국어", "수학", "영어", "사회", "한국사"] * 3
    return [
        {
            "학년": 1 + index // 6,
            "학기": 1 + index % 2,
            "교과": group,
            "과목": f"{group}{index}",
            "이수단위": 2,
            "등급": rank,
            "과목구분": "일반",
        }
        for index, group in enumerate(groups[:12])
    ]


@_skip_no_db
def test_calculate_score_anyang_absent_free_major_row_is_non_calculation() -> None:
    result = calculate_score("268", _subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "ANYANG_2027_NOT_IN_OFFICIAL_GUIDE"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_anyang_sports_science_uses_official_formula_plugin() -> None:
    result = calculate_score("269", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "ANYANG_2027_SPORTS_SCIENCE_RECORD400_PRACTICAL600"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["record_full_score"] == pytest.approx(400.0)
    assert result["practical_full_score"] == pytest.approx(600.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["used_subjects"] == 12
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_anyang_sums_school_violence_deductions() -> None:
    result = calculate_score("269", _subjects(), {"school_violence_measures": [4, 8]}, {})

    assert result["status"] == "calculated"
    assert result["full_practical_total"] == pytest.approx(870.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(870.0)
