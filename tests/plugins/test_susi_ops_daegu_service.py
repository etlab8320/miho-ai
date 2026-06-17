from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    subjects: list[dict[str, object]] = []
    for index, category in enumerate(["국어", "수학", "영어", "사회", "한국사", "과학", "국어", "영어", "수학", "사회"]):
        subjects.append(
            {
                "학년": 1 + index // 4,
                "학기": 1 + index % 2,
                "교과": category,
                "과목": f"{category}{index + 1}",
                "이수단위": 3,
                "등급": "1",
            }
        )
    return subjects


@_skip_no_db
def test_calculate_score_daegu_record_track_uses_official_plugin() -> None:
    result = calculate_score("126", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "DAEGU_2027_ARTSPORT_TOP10_COURSE90_ATT10_RECORD100"
    assert result["student_record_score"] == pytest.approx(1000.0)
    assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_daegu_practical_track_uses_official_plugin() -> None:
    result = calculate_score("127", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "DAEGU_2027_ARTSPORT_TOP10_COURSE90_ATT10_RECORD20_PRACTICAL80"
    assert result["student_record_score"] == pytest.approx(200.0)
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(800.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(1000.0)


@_skip_no_db
def test_calculate_score_daegu_hakjong_and_absent_rows_are_not_numeric() -> None:
    hakjong = calculate_score("129", _subjects(), {}, {})
    absent = calculate_score("131", _subjects(), {}, {})

    assert hakjong["status"] == "non_calculation_track"
    assert hakjong["formula_key"] == "DAEGU_2027_DOCUMENT_QUALITATIVE_NON_CALCULATION"
    assert absent["status"] == "non_calculation_track"
    assert absent["formula_key"] == "DAEGU_2027_NOT_IN_OFFICIAL_GUIDE"
