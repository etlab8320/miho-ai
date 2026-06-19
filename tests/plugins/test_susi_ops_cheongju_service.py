from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "CHEONGJU_2027_ART_SPORTS_RECORD300_PRACTICAL700"
ATHLETE_KEY = "CHEONGJU_2027_ATHLETE_RECORD300_INTERVIEW300_AWARD400"
RECORD1000_KEY = "CHEONGJU_2027_RECORD1000"
INTERVIEW_KEY = "CHEONGJU_2027_RECORD700_INTERVIEW300"


def _subjects() -> list[dict[str, object]]:
    groups = ["국어", "국어", "영어", "영어", "수학", "수학", "사회", "과학"]
    return [
        {
            "학년": 1 + index // 4,
            "학기": 1 + index % 2,
            "교과": group,
            "과목": f"과목{index}",
            "이수단위": 2,
            "등급": "1",
            "원점수": 100.0,
            "평균": 75.0,
            "표준편차": 12.0,
        }
        for index, group in enumerate(groups)
    ]


def _subjects_with_score(raw_score: float) -> list[dict[str, object]]:
    rows = _subjects()
    for row in rows:
        row["원점수"] = raw_score
    return rows


def _career_a_subject() -> dict[str, object]:
    return {
        "학년": 2,
        "학기": 1,
        "교과": "과학",
        "과목": "진로선택A",
        "이수단위": 2,
        "과목유형": "진로선택",
        "성취도": "A",
    }


@_skip_no_db
def test_calculate_score_cheongju_art_sports_uses_official_plugin() -> None:
    result = calculate_score("338", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["used_subjects"] == 8
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["record_full_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_cheongju_absent_and_school_violence_contract() -> None:
    absent = calculate_score("338", _subjects(), {"practical_absent": True}, {})
    deducted = calculate_score("338", _subjects(), {"school_violence_measures": [1, 6]}, {})
    ineligible = calculate_score("338", _subjects(), {"school_violence_measure": 8}, {})

    assert absent["status"] == "cheongju_practical_absent_ineligible"
    assert absent["formula_key"] == FORMULA_KEY
    assert deducted["status"] == "calculated"
    assert deducted["full_practical_total"] == pytest.approx(850.0)
    assert ineligible["status"] == "cheongju_school_violence_ineligible"
    assert ineligible["formula_key"] == FORMULA_KEY


@_skip_no_db
def test_calculate_score_cheongju_extra_tracks_use_official_components() -> None:
    athlete = calculate_score("366", _subjects(), {"unexcused_absence_days": 7}, {})
    record = calculate_score("367", _subjects(), {}, {})
    course_talent = calculate_score("450", _subjects(), {}, {})
    future_talent = calculate_score("451", _subjects(), {}, {})
    regional = calculate_score("368", _subjects(), {}, {})
    interview = calculate_score("369", _subjects(), {}, {})

    assert athlete["formula_key"] == ATHLETE_KEY
    assert athlete["student_record_score"] == pytest.approx(290.0)
    assert athlete["record_full_score"] == pytest.approx(300.0)
    assert athlete["practical_full_score"] == pytest.approx(700.0)
    assert athlete["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
    assert record["formula_key"] == RECORD1000_KEY
    assert record["record_full_score"] == pytest.approx(1000.0)
    assert record["practical_full_score"] == pytest.approx(0.0)
    assert course_talent["formula_key"] == RECORD1000_KEY
    assert course_talent["record_full_score"] == pytest.approx(1000.0)
    assert course_talent["full_practical_total"] == pytest.approx(1000.0)
    assert future_talent["formula_key"] == RECORD1000_KEY
    assert future_talent["record_full_score"] == pytest.approx(1000.0)
    assert future_talent["full_practical_total"] == pytest.approx(1000.0)
    assert regional["formula_key"] == RECORD1000_KEY
    assert regional["record_full_score"] == pytest.approx(1000.0)
    assert interview["formula_key"] == INTERVIEW_KEY
    assert interview["student_record_score"] == pytest.approx(700.0)
    assert interview["record_full_score"] == pytest.approx(700.0)
    assert interview["practical_full_score"] == pytest.approx(300.0)
    assert interview["full_practical_total"] == pytest.approx(1000.0)
    assert interview["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_cheongju_sports_rehab_career_a_bonus() -> None:
    result = calculate_score("367", _subjects_with_score(98.0) + [_career_a_subject()], {}, {})
    life_pe = calculate_score("338", _subjects_with_score(98.0) + [_career_a_subject()], {}, {})

    assert result["formula_key"] == RECORD1000_KEY
    assert result["student_record_score"] == pytest.approx(982.0)
    assert result["full_practical_total"] == pytest.approx(982.0)
    assert life_pe["student_record_score"] == pytest.approx(294.0)
    assert life_pe["full_practical_total"] == pytest.approx(994.0)
