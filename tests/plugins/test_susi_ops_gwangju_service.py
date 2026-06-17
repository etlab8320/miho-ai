from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _full_subjects() -> list[dict[str, object]]:
    subjects: list[dict[str, object]] = []
    for category in ["국어", "영어", "수학", "사회"]:
        for index in range(4):
            subjects.append(
                {
                    "학년": 1,
                    "학기": 1,
                    "교과": category,
                    "과목": f"{category}{index + 1}",
                    "이수단위": 3,
                    "등급": "1",
                }
            )
    return subjects


@_skip_no_db
def test_calculate_score_gwangju_practical_uses_official_formula_plugin() -> None:
    result = calculate_score("102", _full_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "GWANGJU_2027_PRACTICAL_COURSE270_ATT30_PRACTICAL700"
    assert result["student_record_score"] == pytest.approx(300.0)


@_skip_no_db
def test_calculate_score_gwangju_general_uses_official_formula_plugin() -> None:
    result = calculate_score("103", _full_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "GWANGJU_2027_GENERAL_COURSE900_ATT100"
    assert result["student_record_score"] == pytest.approx(1000.0)
