from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    groups = ["국어", "수학", "영어", "사회", "과학", "한국사"]
    return [
        {
            "학년": 1 + index // 6,
            "학기": 1 + index % 2,
            "교과": groups[index % len(groups)],
            "과목": f"일반{index}",
            "이수단위": 3,
            "등급": rank,
            "과목구분": "일반",
        }
        for index in range(12)
    ]


@_skip_no_db
def test_calculate_score_sungkyul_uses_official_formula_plugin() -> None:
    for uid in ("248", "249"):
        result = calculate_score(uid, _subjects(), {}, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "SUNGKYUL_2027_OFFICIAL_PE_RECORD400_PRACTICAL600"
        assert result["student_record_score"] == pytest.approx(400.0)
        assert result["record_full_score"] == pytest.approx(400.0)
        assert result["practical_full_score"] == pytest.approx(600.0)
        assert result["full_practical_total"] == pytest.approx(1000.0)
        assert result["used_subjects"] == 12
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_sungkyul_applies_school_violence_and_ineligible() -> None:
    deducted = calculate_score("248", _subjects(), {"school_violence_measures": [4, 6]}, {})
    ineligible = calculate_score("249", _subjects(), {"school_violence_measure": 9}, {})

    assert deducted["status"] == "calculated"
    assert deducted["full_practical_total"] == pytest.approx(992.0)
    assert deducted["vs_prev_year"]["max_possible_total"] == pytest.approx(992.0)
    assert ineligible["status"] == "sungkyul_school_violence_ineligible"
    assert ineligible["strategy"] == "official_formula_plugin"
