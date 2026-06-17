from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "과학", "과목": "과학", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "체육", "과목": "체육", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "문학", "이수단위": 3, "등급": rank, "과목구분": "일반"},
    ]


@_skip_no_db
def test_calculate_score_yeongsan_practical_uses_official_formula_plugin() -> None:
    result = calculate_score("272", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "YEONGSAN_2027_LEISURE_SPORTS_RECORD300_PRACTICAL700"
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["record_full_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_yeongsan_practical_events_are_capped_to_official_700() -> None:
    result = calculate_score("272", _subjects(), {"practical_event_scores": [350, 347.2]}, {})

    assert result["status"] == "calculated"
    assert result["practical_full_score"] == pytest.approx(697.2)
    assert result["full_practical_total"] == pytest.approx(997.2)


@_skip_no_db
def test_calculate_score_yeongsan_school_violence_single_measure_rate() -> None:
    result = calculate_score("272", _subjects(), {"school_violence_measure": 8}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["full_practical_total"] == pytest.approx(950.0)


@_skip_no_db
def test_calculate_score_yeongsan_practical_absence_is_ineligible() -> None:
    result = calculate_score("272", _subjects(), {"practical_absent": True}, {})

    assert result["status"] == "practical_absent_ineligible"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "YEONGSAN_2027_LEISURE_SPORTS_RECORD300_PRACTICAL700"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
