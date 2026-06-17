from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    categories = ["국어", "수학", "영어", "사회", "과학", "한국사", "기술가정"]
    for index in range(14):
        rows.append(
            {
                "학년": 1 + index // 6,
                "학기": 1 + index % 2,
                "교과": categories[index % len(categories)],
                "과목": f"일반{index}",
                "이수단위": 3,
                "등급": "1",
                "과목구분": "일반",
            }
        )
    for index, credit in enumerate([2, 3, 4, 5]):
        rows.append(
            {
                "학년": 3,
                "학기": 1,
                "교과": "사회",
                "과목": f"진로{index}",
                "이수단위": credit,
                "성취도": "A",
                "과목구분": "진로",
            }
        )
    return rows


@_skip_no_db
def test_calculate_score_sangmyung_seoul_practical_uses_official_plugin() -> None:
    result = calculate_score("214", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "SMU_2027_OFFICIAL_SILGI_RECORD_PRACTICAL"
    assert result["student_record_score"] == pytest.approx(300.0)
    assert result["record_full_score"] == pytest.approx(300.0)
    assert result["practical_full_score"] == pytest.approx(700.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["used_subjects"] == 16
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_sangmyung_cheonan_practical_uses_official_plugin() -> None:
    result = calculate_score("217", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["formula_key"] == "SMU_2027_OFFICIAL_SILGI_RECORD_PRACTICAL"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["record_full_score"] == pytest.approx(400.0)
    assert result["practical_full_score"] == pytest.approx(600.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_sangmyung_comprehensive_tracks_are_noncalc() -> None:
    for uid in ("222", "223", "224"):
        result = calculate_score(uid, _subjects(), {}, {})

        assert result["status"] == "non_calculation_track"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "SMU_2027_STUDENT_COMPREHENSIVE_NON_CALCULATION"
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
