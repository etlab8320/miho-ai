from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    groups = ["국어", "영어", "수학", "사회", "과학", "한국사"] * 2
    semesters = [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 1)] * 2
    rows = [
        {
            "학년": semesters[index][0],
            "학기": semesters[index][1],
            "교과": group,
            "과목": f"{group}{index}",
            "이수단위": 2,
            "등급": rank,
            "과목구분": "일반",
        }
        for index, group in enumerate(groups)
    ]
    rows.extend(
        [
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로A1", "이수단위": 2, "성취도": "A", "성취도분포비율": 0, "과목구분": "진로"},
            {"학년": 2, "학기": 1, "교과": "영어", "과목": "진로A2", "이수단위": 2, "성취도": "A", "성취도분포비율": 0, "과목구분": "진로"},
            {"학년": 2, "학기": 1, "교과": "수학", "과목": "진로A3", "이수단위": 2, "성취도": "A", "성취도분포비율": 0, "과목구분": "진로"},
        ]
    )
    return rows


@_skip_no_db
def test_calculate_score_hoseo_uses_official_formula_plugin() -> None:
    result = calculate_score("397", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "HOSEO_2027_SOCIAL_PE_RECORD200_PRACTICAL800"
    assert result["student_record_score"] == pytest.approx(200.0)
    assert result["record_full_score"] == pytest.approx(200.0)
    assert result["practical_full_score"] == pytest.approx(800.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_hoseo_school_violence_uses_20_percent_column() -> None:
    result = calculate_score("397", _subjects(), {"school_violence_measure": 8}, {})

    assert result["status"] == "calculated"
    assert result["full_practical_total"] == pytest.approx(984.0)
    assert result["vs_prev_year"]["max_possible_total"] == pytest.approx(984.0)


@_skip_no_db
def test_calculate_score_hoseo_graduate_includes_third_grade_second_semester() -> None:
    grades = [
        {"학년": 1 + index % 3, "학기": 1, "교과": "국어", "과목": f"국어{index}", "이수단위": 2, "등급": "9", "과목구분": "일반"}
        for index in range(12)
    ]
    grades.append({"학년": 3, "학기": 2, "교과": "국어", "과목": "졸업자반영국어", "이수단위": 2, "등급": "1", "과목구분": "일반"})

    current = calculate_score("397", grades, {}, {})
    graduate = calculate_score("397", grades, {}, {}, student_context={"graduation_status": "graduate"})

    assert current["student_record_score"] == pytest.approx(0.0)
    assert graduate["student_record_score"] == pytest.approx(60.0)
