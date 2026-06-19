from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _wise_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 4, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "국어", "과목": "국어2", "이수단위": 4, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "국어3", "이수단위": 4, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 4, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "영어", "과목": "영어2", "이수단위": 4, "등급": "1"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "영어3", "이수단위": 4, "등급": "1"},
        {"학년": 3, "학기": 2, "교과": "국어", "과목": "제외3-2", "이수단위": 4, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "제외수학", "이수단위": 4, "등급": "1"},
    ]


def _seoul_subjects() -> list[dict[str, object]]:
    groups = ["국어", "수학", "사회", "과학", "영어", "한국사", "국어", "수학", "사회", "영어"]
    grades = [1, 2, 3, 4, 5, 6, 7, 8, 9, 1]
    credits = [1, 1, 1, 1, 1, 1, 1, 1, 10, 1]
    return [
        {"학년": 1 + index // 5, "학기": 1 + index % 2, "교과": groups[index], "과목": f"과목{index}", "이수단위": credits[index], "등급": str(grades[index])}
        for index in range(10)
    ]


@_skip_no_db
def test_calculate_score_dongguk_wise_record_and_practical_tracks() -> None:
    record = calculate_score("147", _wise_subjects(), {}, {})
    practical = calculate_score("149", _wise_subjects(), {}, {})

    assert record["status"] == "calculated"
    assert record["strategy"] == "official_formula_plugin"
    assert record["formula_key"] == "DGU_WISE_2027_ARTSPORT_KORENG_TOP6_CREDITWEIGHTED_NOCAREER_TO_3_1_RECORD1000"
    assert record["student_record_score"] == pytest.approx(1000.0)
    assert practical["formula_key"] == "DGU_WISE_2027_PRACTICAL_KORENG_TOP6_CREDITWEIGHTED_NOCAREER_TO_3_1_RATIO300"
    assert practical["student_record_score"] == pytest.approx(300.0)
    assert practical["vs_prev_year"]["practical_max"] == pytest.approx(700.0)


@_skip_no_db
def test_calculate_score_dongguk_seoul_pe_uses_no_credit_average() -> None:
    result = calculate_score("155", _seoul_subjects(), {"unexcused_absence_days": 7, "unexcused_late": 1, "unexcused_early_leave": 3}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "DGU_2027_PRACTICAL_TOP10_NOCREDIT_GRADE10BASE_TO_3_1_CAREER_RANKONLY"
    assert result["student_record_score"] == pytest.approx(260.6)
    assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
def test_calculate_score_dongguk_seoul_pe_converts_practical_event_scores() -> None:
    result = calculate_score(
        "155",
        _seoul_subjects(),
        {"practical_event_scores": [100, 100, 100, 100]},
        {},
    )

    assert result["status"] == "calculated"
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(972.6)
