from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, group in enumerate(["국어", "영어", "수학", "사회", "과학", "체육", "예술", "기타"]):
        rows.append(
            {
                "학년": 1 + index // 4,
                "학기": 1 + index % 2,
                "교과": group,
                "과목": f"{group}{index}",
                "이수단위": 1,
                "등급": "1",
            }
        )
    rows.append({"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 1, "성취도": "A", "과목구분": "진로선택"})
    rows.append({"학년": 2, "학기": 2, "교과": "영어", "과목": "진로영어", "이수단위": 1, "성취도": "A", "과목구분": "진로선택"})
    return rows


@_skip_no_db
def test_calculate_score_dongseo_record_interview_and_practical_tracks() -> None:
    record = calculate_score("163", _subjects(), {}, {})
    interview = calculate_score("166", _subjects(), {}, {})
    practical = calculate_score("164", _subjects(), {}, {})

    assert record["status"] == "calculated"
    assert record["strategy"] == "official_formula_plugin"
    assert record["formula_key"] == "DONGSEO_2027_GENERAL_RECORD1000"
    assert record["student_record_score"] == pytest.approx(1000.0)
    assert record["minimum_csat"]["has_minimum"] is False

    assert interview["strategy"] == "official_formula_plugin"
    assert interview["formula_key"] == "DONGSEO_2027_INTERVIEW_RECORD700_INTERVIEW300"
    assert interview["student_record_score"] == pytest.approx(700.0)
    assert interview["used_subjects"] == 10

    assert practical["strategy"] == "official_formula_plugin"
    assert practical["student_record_score"] == pytest.approx(200.0)
    assert practical["used_subjects"] == 10
    assert practical["vs_prev_year"]["practical_max"] == pytest.approx(800.0)


@_skip_no_db
def test_calculate_score_dongseo_noncalc_and_not_in_guide_rows() -> None:
    not_in = calculate_score("162", _subjects(), {}, {})
    comprehensive = calculate_score("167", _subjects(), {}, {})

    assert not_in["status"] == "non_calculation_track"
    assert not_in["strategy"] == "official_formula_plugin"
    assert not_in["formula_key"] == "DONGSEO_2027_NOT_IN_OFFICIAL_GUIDE"
    assert not_in["minimum_csat"]["has_minimum"] is False

    assert comprehensive["status"] == "non_calculation_track"
    assert comprehensive["strategy"] == "official_formula_plugin"
    assert comprehensive["formula_key"] == "DONGSEO_2027_NON_CALCULATION_TRACK"
