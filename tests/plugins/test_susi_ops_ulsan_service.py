from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    regular_groups = ["국어", "국어", "영어", "영어", "수학", "수학", "사회", "과학"]
    for index, group in enumerate(regular_groups):
        rows.append(
            {
                "학년": 1 + (index // 4),
                "학기": 1 + (index % 2),
                "교과": group,
                "과목": f"{group}{index}",
                "이수단위": 2,
                "등급": rank,
                "과목구분": "일반",
            }
        )
    rows.extend(
        [
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
            {"학년": 2, "학기": 1, "교과": "영어", "과목": "진로영어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
            {"학년": 2, "학기": 1, "교과": "수학", "과목": "진로수학", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        ]
    )
    return rows


@_skip_no_db
def test_calculate_score_ulsan_regular_uses_official_formula_plugin() -> None:
    result = calculate_score("303", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "ULSAN_2027_SPORTS_RECORD400_PRACTICAL600"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["record_full_score"] == pytest.approx(400.0)
    assert result["practical_full_score"] == pytest.approx(600.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["used_subjects"] == 9
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_ulsan_rural_attendance_and_practical_are_reflected() -> None:
    attendance = {"unexcused_absence_days": 1, "practical_event_scores": [200, 197, 194]}
    result = calculate_score("298", _subjects("2"), attendance, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(397.5)
    assert result["record_full_score"] == pytest.approx(400.0)
    assert result["practical_full_score"] == pytest.approx(591.0)
    assert result["full_practical_total"] == pytest.approx(988.5)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
