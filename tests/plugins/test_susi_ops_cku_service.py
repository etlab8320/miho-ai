from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "CKU_2027_TOP12_CAREER_MAX2_ABC_124_CREDIT_WEIGHTED_TO_3_1"


def _perfect_subjects() -> list[dict[str, object]]:
    groups = ["국어", "영어", "수학", "사회", "과학", "한국사"] * 2
    return [
        {
            "학년": 1 if index < 6 else 2,
            "학기": 1,
            "교과": group,
            "과목": f"{group}{index}",
            "이수단위": 1,
            "등급": "1",
            "과목구분": "일반",
        }
        for index, group in enumerate(groups)
    ]


@_skip_no_db
def test_calculate_score_cku_pe_education_uses_official_700_300_split() -> None:
    result = calculate_score("4", _perfect_subjects(), {"unexcused_absence_days": 31}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(700.0)
    assert result["record_full_score"] == pytest.approx(700.0)
    assert result["practical_full_score"] == pytest.approx(300.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_cku_rehab_uses_official_600_400_split() -> None:
    result = calculate_score("3", _perfect_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(600.0)
    assert result["record_full_score"] == pytest.approx(600.0)
    assert result["practical_full_score"] == pytest.approx(400.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
