from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, group in enumerate(["국어", "영어", "수학", "사회", "과학"]):
        rows.append({"학년": 1, "학기": 1, "교과": group, "과목": f"{group}{index}", "이수단위": 3, "등급": "1"})
    for index in range(3):
        rows.append({"학년": 2, "학기": 1, "교과": "국어", "과목": f"진로{index}", "이수단위": 3, "성취도": "A", "과목구분": "진로선택"})
    return rows


def _subjects_with_ranked_career() -> list[dict[str, object]]:
    rows = [
        {"학년": 1, "학기": 1, "교과": group, "과목": group, "이수단위": 3, "등급": "1", "과목구분": "일반"}
        for group in ["국어", "영어", "수학", "사회"]
    ]
    rows.extend(
        [
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로병기A", "이수단위": 3, "등급": "1", "성취도": "A", "과목구분": "진로선택"},
            {"학년": 2, "학기": 1, "교과": "영어", "과목": "진로A", "이수단위": 3, "성취도": "A", "과목구분": "진로선택"},
            {"학년": 2, "학기": 1, "교과": "사회", "과목": "진로B", "이수단위": 3, "성취도": "B", "과목구분": "진로선택"},
        ]
    )
    return rows


@_skip_no_db
def test_calculate_score_mokwon_tracks_use_official_plugin() -> None:
    practical = calculate_score("182", _subjects(), {}, {})
    course = calculate_score("183", _subjects(), {}, {})
    regional = calculate_score("184", _subjects(), {}, {})

    assert practical["status"] == "calculated"
    assert practical["strategy"] == "official_formula_plugin"
    assert practical["formula_key"] == "MOKWON_2027_OFFICIAL_TOP5_CAREER3_DENOM785"
    assert practical["student_record_score"] == pytest.approx(100.0)
    assert practical["used_subjects"] == 8
    assert practical["minimum_csat"]["has_minimum"] is False
    assert practical["vs_prev_year"]["practical_max"] == pytest.approx(900.0)

    assert course["strategy"] == "official_formula_plugin"
    assert course["student_record_score"] == pytest.approx(1000.0)
    assert regional["strategy"] == "official_formula_plugin"
    assert regional["student_record_score"] == pytest.approx(1000.0)


@_skip_no_db
@pytest.mark.parametrize("university_id", ["458", "459"])
def test_calculate_score_mokwon_education_practical_tracks_use_400_600_scale(university_id: str) -> None:
    result = calculate_score(university_id, _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "MOKWON_2027_OFFICIAL_TOP5_CAREER3_DENOM785"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["record_full_score"] == pytest.approx(400.0)
    assert result["practical_full_score"] == pytest.approx(600.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)


@_skip_no_db
def test_calculate_score_mokwon_ranked_career_subject_defaults_to_c_grade() -> None:
    result = calculate_score("183", _subjects_with_ranked_career(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(917.2)
    assert result["average_grade"] == pytest.approx(2.75)
