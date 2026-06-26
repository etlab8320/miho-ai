"""Susi grade-engine tests for generic central subject categories."""

from __future__ import annotations

import pytest

from plugins.susi_ops.grade_engine import _subject_allowed, _weighted_average_grade


def test_subject_allowed_infers_area_from_subject_when_central_category_is_generic() -> None:
    row = {"교과": "일반", "과목": "화법과 작문"}
    assert _subject_allowed(row, {"국어": "O", "기타": "X"}) is True

    science_row = {"교과": "일반", "과목": "통합과학"}
    assert _subject_allowed(science_row, {"과학": "O", "기타": "X"}) is True


def test_weighted_average_grade_uses_subject_name_for_generic_central_categories() -> None:
    grades = [
        {"교과": "일반", "과목": "화법과 작문", "등급": "6", "이수단위": "4", "과목구분": "일반"},
        {"교과": "일반", "과목": "확률과 통계", "등급": "8", "이수단위": "4", "과목구분": "일반"},
        {"교과": "일반", "과목": "정보", "등급": "1", "이수단위": "4", "과목구분": "일반"},
        {"교과": "진로 선택", "과목": "스포츠 생활", "성취도": "A", "이수단위": "2", "과목구분": "진로 선택"},
    ]
    score_logic = {
        "subject_flags": {"국어": "O", "수학": "O", "체육": "O", "기타": "X"},
        "career_subjects": "O",
        "max_career_subjects": 1,
    }

    avg, used, total, _ = _weighted_average_grade(grades, score_logic)

    assert avg == pytest.approx((6 * 4 + 8 * 4 + 1 * 2) / 10)
    assert used == 3
    assert total == pytest.approx(10)
