from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    return [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1", "과목구분": "일반"},
        {"학년": 1, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": "1", "과목구분": "일반"},
    ]


@_skip_no_db
def test_calculate_score_sookmyung_uses_official_formula_plugin() -> None:
    result = calculate_score("255", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SOOKMYUNG_2027_ART_CREATIVE_PE_RECORD400_PRACTICAL600"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["record_full_score"] == pytest.approx(400.0)
    assert result["practical_full_score"] == pytest.approx(600.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_sookmyung_practical_minimum_and_violence_cap() -> None:
    result = calculate_score(
        "255",
        _subjects(),
        {"practical_score": 0, "school_violence_measures": [1, 4, 8]},
        {},
    )

    assert result["status"] == "calculated"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["practical_full_score"] == pytest.approx(120.0)
    assert result["full_practical_total"] == pytest.approx(420.0)


@_skip_no_db
def test_calculate_score_sookmyung_missing_required_group_is_not_calculated() -> None:
    subjects = [row for row in _subjects() if row["교과"] != "한국사"]
    result = calculate_score("255", subjects, {}, {})

    assert result["status"] == "missing_required_subjects_ineligible"
    assert result["strategy"] == "official_formula_plugin"
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
