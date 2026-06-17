from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    groups = ["국어", "수학", "영어", "사회", "과학", "한국사"]
    return [
        {"학년": 1 + index // 6, "학기": 1 if index >= 12 else 1 + index % 2, "교과": groups[index % len(groups)], "과목": f"일반{index}", "이수단위": 2, "등급": "1"}
        for index in range(18)
    ]


@_skip_no_db
def test_calculate_score_pusan_pe_practical_tracks_use_official_plugin() -> None:
    for uid in ("202", "203", "204"):
        result = calculate_score(uid, _subjects(), {}, {})
        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "PUSAN_2027_OFFICIAL_COURSE_PRACTICAL_QUALITATIVE"
        assert result["student_record_score"] == pytest.approx(40.0)
        assert result["used_subjects"] == 18
        assert result["vs_prev_year"]["practical_max"] == pytest.approx(60.0)


@_skip_no_db
def test_calculate_score_pusan_minimum_csat_by_track() -> None:
    assert calculate_score("202", _subjects(), {}, {})["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
    assert calculate_score("203", _subjects(), {}, {})["minimum_csat"] == {
        "has_minimum": True,
        "detail": "상위 2개 영역 등급 합 6 이내, 한국사 4등급 이내",
    }
    assert calculate_score("204", _subjects(), {}, {})["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
    assert calculate_score("210", _subjects(), {}, {})["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
    assert calculate_score("211", _subjects(), {}, {})["minimum_csat"] == {
        "has_minimum": True,
        "detail": "상위 2개 영역 등급 합 5 이내, 한국사 4등급 이내",
    }
    assert calculate_score("211", _subjects(), {}, {})["used_subjects"] == 18


@_skip_no_db
def test_calculate_score_pusan_social_consideration_is_noncalc() -> None:
    result = calculate_score("210", _subjects(), {}, {})

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "PUSAN_2027_SOCIAL_CONSIDERATION_NON_CALCULATION"


@_skip_no_db
def test_calculate_score_pusan_graduate_context_includes_grade3_semester2() -> None:
    subjects = [
        {"학년": 3, "학기": 1, "교과": "국어", "과목": "졸업예정반영", "이수단위": 2, "등급": "1"},
        {"학년": 3, "학기": 2, "교과": "국어", "과목": "졸업자추가반영", "이수단위": 2, "등급": "9"},
    ]
    current = calculate_score("203", subjects, {}, {}, {"is_graduate": False})
    graduate = calculate_score("203", subjects, {}, {}, {"is_graduate": True})

    assert current["student_record_score"] == pytest.approx(40.0)
    assert graduate["student_record_score"] == pytest.approx(20.0)
