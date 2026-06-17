from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects(rank: str = "1", achievement: str = "A") -> list[dict[str, object]]:
    subjects = [
        ("국어", "국어", 4, "공통"),
        ("수학", "수학", 4, "공통"),
        ("영어", "영어", 4, "공통"),
        ("사회", "통합사회", 3, "공통"),
        ("과학", "통합과학", 3, "공통"),
        ("한국사", "한국사", 3, "공통"),
        ("국어", "문학", 4, "일반"),
        ("영어", "영어I", 4, "일반"),
        ("사회", "사회문화", 3, "일반"),
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


@_skip_no_db
def test_calculate_score_chosun_practical_track_uses_no_attendance_component() -> None:
    result = calculate_score(
        "333",
        _subjects(rank="2", achievement="B"),
        {"unexcused_absence_days": 2},
        {},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "CHOSUN_2027_OFFICIAL_RECORD500_PRACTICAL500"
    assert result["student_record_score"] == pytest.approx(494.0)
    assert result["record_full_score"] == pytest.approx(500.0)
    assert result["practical_full_score"] == pytest.approx(500.0)
    assert result["full_practical_total"] == pytest.approx(994.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_chosun_sports_industry_defaults_to_confirmed_general_practical() -> None:
    calculated = calculate_score("332", _subjects(), {}, {})

    assert calculated["status"] == "calculated"
    assert calculated["full_practical_total"] == pytest.approx(1000.0)
    assert calculated["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
