from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

PRACTICAL_FORMULA_KEY = "YIU_2027_ARTSPORT_TOP3_PER_GRADE_DISTINCT_COURSE_RECORD30_FITNESS70"
RECORD100_FORMULA_KEY = "YIU_2027_ARTSPORT_TOP3_PER_GRADE_DISTINCT_COURSE_RECORD100"


def _subjects() -> list[dict[str, object]]:
    rows = []
    for grade in (1, 2, 3):
        for group in ("국어", "영어", "수학"):
            rows.append({
                "학년": grade,
                "학기": 1,
                "교과": group,
                "과목": f"{group}{grade}",
                "이수단위": 3,
                "등급": "1",
                "과목구분": "일반",
            })
    return rows


@_skip_no_db
def test_calculate_score_yongin_practical_uses_official_formula_plugin() -> None:
    result = calculate_score("276", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == PRACTICAL_FORMULA_KEY
    assert result["used_subjects"] == 9
    assert result["student_record_score"] == pytest.approx(150.0)
    assert result["record_full_score"] == pytest.approx(150.0)
    assert result["practical_full_score"] == pytest.approx(350.0)
    assert result["full_practical_total"] == pytest.approx(500.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_yongin_record100_rows_are_calculated() -> None:
    result = calculate_score("290", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == RECORD100_FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(500.0)
    assert result["record_full_score"] == pytest.approx(500.0)
    assert result["practical_full_score"] == pytest.approx(0.0)
    assert result["full_practical_total"] == pytest.approx(500.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_yongin_school_violence_measures_are_summed() -> None:
    result = calculate_score(
        "276",
        _subjects(),
        {"practical_event_scores": [170, 165], "school_violence_measures": [4, 8]},
        {},
    )

    assert result["status"] == "calculated"
    assert result["practical_full_score"] == pytest.approx(335.0)
    assert result["full_practical_total"] == pytest.approx(425.0)


@_skip_no_db
def test_calculate_score_yongin_practical_absence_is_ineligible() -> None:
    result = calculate_score("276", _subjects(), {"practical_absent": True}, {})

    assert result["status"] == "practical_absent_ineligible"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == PRACTICAL_FORMULA_KEY
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
