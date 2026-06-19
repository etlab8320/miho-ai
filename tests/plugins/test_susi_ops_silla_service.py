from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects(rank: str = "1") -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "과학", "과목": "과학", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "국어", "과목": "문학", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "수학", "과목": "수학I", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "영어", "과목": "영어I", "이수단위": 3, "등급": rank, "과목구분": "일반"},
        {"학년": 2, "학기": 1, "교과": "사회", "과목": "사회문화", "이수단위": 3, "등급": rank, "과목구분": "일반"},
    ]


@_skip_no_db
def test_calculate_score_silla_practical_uses_official_formula_plugin() -> None:
    result = calculate_score("265", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SILLA_2027_PRACTICAL_RECORD250_PRACTICAL750"
    assert result["student_record_score"] == pytest.approx(250.0)
    assert result["record_full_score"] == pytest.approx(250.0)
    assert result["practical_full_score"] == pytest.approx(750.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_silla_practical_raw_100_point_events_scale_to_250_each() -> None:
    result = calculate_score("265", _subjects(), {"practical_event_scores": [100, 96, 96, 0]}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(250.0)
    assert result["practical_full_score"] == pytest.approx(730.0)
    assert result["full_practical_total"] == pytest.approx(980.0)


@_skip_no_db
def test_calculate_score_silla_record100_tracks_use_official_formula_plugin() -> None:
    for university_id in ("271", "279"):
        result = calculate_score(university_id, _subjects("2"), {}, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "SILLA_2027_RECORD1000"
        assert result["student_record_score"] == pytest.approx(980.0)
        assert result["record_full_score"] == pytest.approx(1000.0)
        assert result["full_practical_total"] == pytest.approx(980.0)
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_silla_school_violence_uses_highest_measure() -> None:
    result = calculate_score("265", _subjects(), {"school_violence_measures": [1, 4, 8]}, {})

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(250.0)
    assert result["full_practical_total"] == pytest.approx(950.0)
