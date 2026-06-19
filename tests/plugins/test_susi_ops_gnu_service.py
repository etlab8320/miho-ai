from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path


_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    regular = [
        (1, 1, "국어", "국어", 4),
        (1, 1, "영어", "영어", 4),
        (1, 1, "사회", "통합사회", 3),
        (1, 1, "과학", "통합과학", 3),
        (1, 1, "한국사", "한국사", 2),
        (2, 1, "국어", "문학", 4),
        (2, 1, "영어", "영어I", 4),
        (2, 1, "사회", "생활과윤리", 3),
        (2, 1, "과학", "생명과학I", 3),
        (2, 2, "국어", "독서", 4),
        (2, 2, "영어", "영어II", 4),
        (2, 2, "사회", "사회문화", 3),
        (2, 2, "과학", "지구과학I", 3),
        (3, 1, "국어", "화법과작문", 4),
        (3, 1, "영어", "영어독해", 4),
        (3, 1, "사회", "윤리와사상", 3),
        (3, 1, "과학", "생활과과학", 3),
        (3, 1, "과학", "과학탐구", 8),
        (3, 1, "수학", "수학과제탐구", 3),
    ]
    for grade, semester, category, subject, credit in regular:
        rows.append(
            {
                "학년": grade,
                "학기": semester,
                "교과": category,
                "과목": subject,
                "이수단위": credit,
                "등급": "1",
            }
        )
    for category, subject in [("국어", "심화국어"), ("영어", "진로영어"), ("사회", "고전과윤리"), ("과학", "물리II")]:
        for index in range(3):
            rows.append(
                {
                    "학년": 3,
                    "학기": 1,
                    "교과": category,
                    "과목": f"{subject}{index + 1}",
                    "이수단위": 2,
                    "등급": "",
                    "성취도": "A",
                    "교과구분": "진로",
                }
            )
    return rows


@_skip_no_db
def test_calculate_score_gnu_physical_education_has_csat_minimum_and_800_200_contract() -> None:
    result = calculate_score("36", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == "GNU_2027_OFFICIAL_ARTS_PE_RECORD_PRACTICAL"
    assert result["student_record_score"] == pytest.approx(800.4)
    assert result["record_full_score"] == pytest.approx(800.0)
    assert result["practical_full_score"] == pytest.approx(200.0)
    assert result["full_practical_total"] == pytest.approx(1000.4)
    assert result["minimum_csat"]["has_minimum"] is True
    assert "2개영역 합 8등급" in result["minimum_csat"]["detail"]


@_skip_no_db
def test_calculate_score_gnu_sports_healthcare_has_no_csat_minimum_and_700_300_contract() -> None:
    result = calculate_score("37", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(700.35)
    assert result["record_full_score"] == pytest.approx(700.0)
    assert result["practical_full_score"] == pytest.approx(300.0)
    assert result["full_practical_total"] == pytest.approx(1000.35)
    assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_gnu_school_violence_uses_highest_measure() -> None:
    result = calculate_score("37", _subjects(), {"school_violence_measures": [1, 4]}, {})

    assert result["status"] == "calculated"
    assert result["full_practical_total"] == pytest.approx(970.35)
