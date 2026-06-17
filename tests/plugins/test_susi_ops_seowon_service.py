from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

PE_EDU_MINIMUM_CSAT = (
    "수능 국어, 수학, 영어, 탐구(사탐, 과탐, 직탐) 중 상위 2개 영역 등급의 합이 "
    "8등급 이내 (탐구는 상위 1과목 등급 반영)"
)

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _perfect_subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어2", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학1", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학2", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어2", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회1", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "과학", "과목": "과학1", "이수단위": 3, "등급": "1"},
    ]


@_skip_no_db
def test_calculate_score_seowon_official_plugins_cover_all_tracks() -> None:
    subjects = _perfect_subjects()
    attendance = {"unexcused_absence_days": 7, "unexcused_late": 1, "unexcused_early_leave": 3}

    expected = {
        "232": ("SEOWON_2027_TOP8_COURSE_20_PRACTICAL80", 200.0, 200.0, 800.0, False),
        "235": ("SEOWON_2027_TOP8_COURSE100", 1000.0, 1000.0, 0.0, False),
        "236": ("SEOWON_2027_TOP8_COURSE100", 1000.0, 1000.0, 0.0, False),
        "237": ("SEOWON_2027_TOP8_COURSE10_ATTENDANCE10_OTHER80", 200.0, 200.0, 800.0, False),
        "238": ("SEOWON_2027_PE_EDU_GENERAL_COURSE60_PRACTICAL40", 600.0, 600.0, 400.0, True),
        "239": ("SEOWON_2027_TOP8_COURSE100", 1000.0, 1000.0, 0.0, False),
        "240": ("SEOWON_2027_TOP8_COURSE55_INTERVIEW45", 550.0, 550.0, 450.0, False),
        "241": ("SEOWON_2027_TOP8_COURSE10_ATTENDANCE10_OTHER80", 200.0, 200.0, 800.0, False),
        "242": ("SEOWON_2027_TOP8_COURSE_20_PRACTICAL80", 200.0, 200.0, 800.0, False),
        "243": ("SEOWON_2027_TOP8_COURSE100", 1000.0, 1000.0, 0.0, False),
        "244": ("SEOWON_2027_TOP8_COURSE100", 1000.0, 1000.0, 0.0, False),
        "245": ("SEOWON_2027_TOP8_COURSE100", 1000.0, 1000.0, 0.0, False),
        "250": ("SEOWON_2027_TOP8_COURSE100", 1000.0, 1000.0, 0.0, False),
        "251": ("SEOWON_2027_TOP8_COURSE10_ATTENDANCE10_OTHER80", 200.0, 200.0, 800.0, False),
        "252": ("SEOWON_2027_TOP8_COURSE100", 1000.0, 1000.0, 0.0, False),
        "258": ("SEOWON_2027_TOP8_COURSE55_INTERVIEW45", 550.0, 550.0, 450.0, False),
        "261": ("SEOWON_2027_TOP8_COURSE100", 1000.0, 1000.0, 0.0, False),
    }

    for uid, (formula_key, record_score, record_full, practical_full, has_minimum) in expected.items():
        result = calculate_score(uid, subjects, attendance, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == formula_key
        assert result["used_subjects"] == 8
        assert result["student_record_score"] == pytest.approx(record_score)
        assert result["record_full_score"] == pytest.approx(record_full)
        assert result["practical_full_score"] == pytest.approx(practical_full)
        assert result["full_practical_total"] == pytest.approx(record_score + practical_full)
        assert result["minimum_csat"]["has_minimum"] is has_minimum
        if has_minimum:
            assert result["minimum_csat"]["detail"] == PE_EDU_MINIMUM_CSAT
        else:
            assert result["minimum_csat"]["detail"] == "없음"
