from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in ["국어", "영어", "수학", "사회"]:
        for index in range(3):
            rows.append(
                {
                    "학년": 1 + (index // 2),
                    "학기": 1 + (index % 2),
                    "교과": group,
                    "과목": f"{group}{index}",
                    "이수단위": 1,
                    "등급": rank,
                    "과목구분": "일반",
                }
            )
    rows.extend(
        [
            {"학년": 1, "학기": 1, "교과": "과학", "과목": "통합과학", "이수단위": 5, "등급": "1", "과목구분": "일반"},
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 5, "성취도": "A", "과목구분": "진로"},
        ]
    )
    return rows


@_skip_no_db
def test_calculate_score_seokyeong_uses_official_formula_plugin() -> None:
    result = calculate_score("221", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SEOKYEONG_2027_SPORTSTECH_RECORD200_PRACTICAL800"
    assert result["student_record_score"] == pytest.approx(200.0)
    assert result["record_full_score"] == pytest.approx(200.0)
    assert result["practical_full_score"] == pytest.approx(800.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["used_subjects"] == 12
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_seokyeong_comparative_record_uses_practical_score() -> None:
    result = calculate_score("221", [], {"comparative_record": True, "practical_score": 784}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(196.0)
    assert result["record_full_score"] == pytest.approx(200.0)
    assert result["practical_full_score"] == pytest.approx(784.0)
    assert result["full_practical_total"] == pytest.approx(980.0)
