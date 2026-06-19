from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in ["국어", "영어", "수학", "사회"]:
        for index in range(3):
            rows.append(
                {
                    "학년": 1,
                    "학기": 1 + index % 2,
                    "교과": group,
                    "과목": f"{group}{index}",
                    "이수단위": 3,
                    "등급": "1",
                }
            )
    return rows


@_skip_no_db
def test_calculate_score_donga_athletics_uses_official_plugin() -> None:
    result = calculate_score("174", _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "DONGA_2027_ATHLETICS_RECORD400_PRACTICAL600"
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["used_subjects"] == 12
    assert result["minimum_csat"]["has_minimum"] is False
    assert result["vs_prev_year"]["practical_max"] == pytest.approx(600.0)


@_skip_no_db
def test_calculate_score_donga_holistic_tracks_are_official_noncalc() -> None:
    for uid in ("175", "176", "178"):
        result = calculate_score(uid, _subjects(), {}, {})
        assert result["status"] == "non_calculation_track"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "DONGA_2027_NON_CALCULATION_TRACK"
        assert result["minimum_csat"]["has_minimum"] is False


@_skip_no_db
@pytest.mark.parametrize(
    ("university_id", "formula_key", "record_full", "practical_full"),
    [
        ("460", "DONGA_2027_ARTDESIGN_RECORD300_PRACTICAL700", 300.0, 700.0),
        ("461", "DONGA_2027_ARTDESIGN_RECORD300_PRACTICAL700", 300.0, 700.0),
        ("462", "DONGA_2027_MUSIC_RECORD200_PRACTICAL800", 200.0, 800.0),
    ],
)
def test_calculate_score_donga_non_athletics_arts_tracks_use_department_scale(
    university_id: str,
    formula_key: str,
    record_full: float,
    practical_full: float,
) -> None:
    result = calculate_score(university_id, _subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == formula_key
    assert result["student_record_score"] == pytest.approx(record_full)
    assert result["record_full_score"] == pytest.approx(record_full)
    assert result["practical_full_score"] == pytest.approx(practical_full)
    assert result["full_practical_total"] == pytest.approx(1000.0)
