from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

PRACTICAL_FORMULA_KEY = "WOOSUK_2027_PRACTICAL_TOP10_CREDIT_WEIGHTED_RECORD40_PRACTICAL240_INTERVIEW120"
COURSE_FORMULA_KEY = "WOOSUK_2027_COURSE_TOP10_CREDIT_WEIGHTED_RECORD400_PLUS_CAREER10"


def _subjects() -> list[dict[str, object]]:
    terms = [
        (1, 1, "국어"),
        (1, 2, "수학"),
        (2, 1, "영어"),
        (2, 2, "사회"),
        (3, 1, "과학"),
        (3, 1, "한국사"),
        (1, 1, "국어"),
        (1, 2, "수학"),
        (2, 1, "영어"),
        (2, 2, "사회"),
    ]
    rows = [
        {
            "학년": grade,
            "학기": semester,
            "교과": group,
            "과목": f"{group}{idx}",
            "이수단위": 2,
            "등급": "1",
            "과목구분": "일반",
        }
        for idx, (grade, semester, group) in enumerate(terms)
    ]
    rows.append({
        "학년": 2,
        "학기": 1,
        "교과": "국어",
        "과목": "진로국어",
        "이수단위": 1,
        "성취도": "A",
        "과목구분": "진로",
    })
    return rows


@_skip_no_db
def test_calculate_score_woosuk_practical_uses_official_formula_plugin() -> None:
    result = calculate_score("285", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == PRACTICAL_FORMULA_KEY
    assert result["used_subjects"] == 10
    assert result["student_record_score"] == pytest.approx(40.0)
    assert result["record_full_score"] == pytest.approx(40.0)
    assert result["practical_full_score"] == pytest.approx(360.0)
    assert result["full_practical_total"] == pytest.approx(400.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_woosuk_practical_contract_applies_to_special_tracks() -> None:
    for university_id in ("286", "287", "293", "295"):
        result = calculate_score(university_id, _subjects(), {}, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == PRACTICAL_FORMULA_KEY
        assert result["full_practical_total"] == pytest.approx(400.0)


@_skip_no_db
def test_calculate_score_woosuk_course_rows_are_calculated_with_career_bonus() -> None:
    for university_id in ("297", "299", "300"):
        result = calculate_score(university_id, _subjects(), {}, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == COURSE_FORMULA_KEY
        assert result["used_subjects"] == 10
        assert result["student_record_score"] == pytest.approx(410.0)
        assert result["record_full_score"] == pytest.approx(410.0)
        assert result["practical_full_score"] == pytest.approx(0.0)
        assert result["full_practical_total"] == pytest.approx(410.0)
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_woosuk_school_violence_highest_measure_only() -> None:
    result = calculate_score(
        "285",
        _subjects(),
        {"practical_event_scores": [70, 70, 70], "interview_score": 100, "school_violence_measures": [1, 4, 8]},
        {},
    )

    assert result["status"] == "calculated"
    assert result["practical_full_score"] == pytest.approx(310.0)
    assert result["full_practical_total"] == pytest.approx(320.0)


@_skip_no_db
def test_calculate_score_woosuk_ineligible_statuses() -> None:
    violence = calculate_score("285", _subjects(), {"school_violence_measure": 9}, {})
    absent = calculate_score("285", _subjects(), {"practical_absent": True}, {})

    assert violence["status"] == "school_violence_ineligible"
    assert violence["formula_key"] == PRACTICAL_FORMULA_KEY
    assert violence["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
    assert absent["status"] == "practical_absent_ineligible"
    assert absent["formula_key"] == PRACTICAL_FORMULA_KEY
    assert absent["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
