from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

PRACTICAL_KEY = "JUNGBU_2027_PRACTICAL_RECORD20_PRACTICAL80"
RECORD100_KEY = "JUNGBU_2027_RECORD100"


def _subjects(rank: str = "1", achievement: str = "A") -> list[dict[str, object]]:
    subjects = [
        ("국어", "국어", 4, "일반"),
        ("영어", "영어", 4, "일반"),
        ("수학", "수학", 4, "일반"),
        ("사회", "통합사회", 3, "일반"),
        ("과학", "통합과학", 3, "일반"),
        ("한국사", "한국사", 3, "일반"),
        ("국어", "문학", 4, "일반"),
    ]
    rows = [
        {
            "학년": 1 + index // 6,
            "학기": 1 + index % 2,
            "교과": category,
            "과목": subject,
            "이수단위": credit,
            "등급": rank,
            "과목구분": course_type,
        }
        for index, (category, subject, credit, course_type) in enumerate(subjects)
    ]
    rows.extend(
        [
            {"학년": 3, "학기": 1, "교과": "국어", "과목": "심화국어", "이수단위": 2, "성취도": achievement, "과목구분": "진로"},
            {"학년": 3, "학기": 1, "교과": "영어", "과목": "진로영어", "이수단위": 2, "성취도": achievement, "과목구분": "진로"},
            {"학년": 3, "학기": 1, "교과": "과학", "과목": "생활과과학", "이수단위": 2, "성취도": achievement, "과목구분": "진로"},
        ]
    )
    return rows


def _mixed_record100_subjects() -> list[dict[str, object]]:
    grades = ["2", "2", "2", "2", "2", "3", "3", "3", "3", "3"]
    groups = ["국어", "영어", "수학", "사회", "과학"] * 2
    terms = [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1)] * 2
    return [
        {
            "학년": terms[index][0],
            "학기": terms[index][1],
            "교과": group,
            "과목": f"{group}{index + 1}",
            "이수단위": 1,
            "등급": grade,
            "과목구분": "일반",
        }
        for index, (group, grade) in enumerate(zip(groups, grades))
    ]


@_skip_no_db
def test_calculate_score_jungbu_practical_tracks_use_official_plugin() -> None:
    for uid in ["334", "335", "336"]:
        result = calculate_score(uid, _subjects(rank="1", achievement="A"), {"unexcused_absence_days": 7}, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == PRACTICAL_KEY
        assert result["used_subjects"] == 10
        assert result["student_record_score"] == pytest.approx(200.0)
        assert result["record_full_score"] == pytest.approx(200.0)
        assert result["practical_full_score"] == pytest.approx(800.0)
        assert result["full_practical_total"] == pytest.approx(1000.0)
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_jungbu_record100_mixed_grades_use_average_band_table() -> None:
    result = calculate_score("358", _mixed_record100_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == RECORD100_KEY
    assert result["average_grade"] == pytest.approx(2.5)
    assert result["student_record_score"] == pytest.approx(940.0)
    assert result["full_practical_total"] == pytest.approx(940.0)


@_skip_no_db
def test_calculate_score_jungbu_record100_tracks_are_numeric() -> None:
    for uid in ["358", "359", "360"]:
        result = calculate_score(uid, _subjects(rank="2", achievement="A"), {}, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == RECORD100_KEY
        assert result["used_subjects"] == 10
        assert result["student_record_score"] == pytest.approx(980.0)
        assert result["record_full_score"] == pytest.approx(1000.0)
        assert result["practical_full_score"] == pytest.approx(0.0)
        assert result["full_practical_total"] == pytest.approx(980.0)
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
