from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "JEONNAM_2027_PE_EDU_RECORD800_PRACTICAL200"
MINIMUM_DETAIL = "국어, 수학, 영어, 탐구(1과목) 중 2개 영역 합 7등급 이내"


def _subjects() -> list[dict[str, object]]:
    rows = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 2, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 2, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 2, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 2, "등급": "1", "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "사회", "과목": "제외사회", "이수단위": 9, "등급": "9", "과목구분": "일반"},
    ]
    rows.extend([
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로국어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "진로영어", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
        {"학년": 3, "학기": 1, "교과": "수학", "과목": "진로수학", "이수단위": 2, "성취도": "A", "과목구분": "진로"},
    ])
    return rows


@_skip_no_db
def test_calculate_score_jeonnam_uses_official_formula_plugin() -> None:
    result = calculate_score("317", _subjects(), {"unexcused_absence_days": 0}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["used_subjects"] == 7
    assert result["student_record_score"] == pytest.approx(800.0)
    assert result["record_full_score"] == pytest.approx(800.0)
    assert result["practical_full_score"] == pytest.approx(200.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": True, "detail": MINIMUM_DETAIL}
    assert result["subject_flags"]["사회"] == "X"
    assert result["subject_flags"]["과학"] == "X"


@_skip_no_db
def test_calculate_score_jeonnam_attendance_and_school_violence_are_applied() -> None:
    result = calculate_score(
        "317",
        _subjects(),
        {"unexcused_absence_days": 1, "unexcused_late": 5, "unexcused_early_leave": 1, "school_violence_measures": [3, 6]},
        {},
    )

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(798.857)
    assert result["full_practical_total"] == pytest.approx(978.857)


@_skip_no_db
def test_calculate_score_jeonnam_practical_absence_is_ineligible() -> None:
    result = calculate_score("317", _subjects(), {"practical_event_absent": True}, {})

    assert result["status"] == "practical_absent_ineligible"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["minimum_csat"] == {"has_minimum": True, "detail": MINIMUM_DETAIL}
