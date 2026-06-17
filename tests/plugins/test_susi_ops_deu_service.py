from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    categories = ["국어", "수학", "영어", "한국사", "사회", "과학"]
    for index in range(12):
        rows.append(
            {
                "학년": 1 + index // 6,
                "학기": 1 + index % 2,
                "교과": categories[index % len(categories)],
                "과목": f"과목{index}",
                "이수단위": 2,
                "등급": "1",
            }
        )
    return rows


@_skip_no_db
def test_calculate_score_deu_practical_tracks_use_official_plugin() -> None:
    leisure = calculate_score("177", _subjects(), {}, {})
    physical = calculate_score("179", _subjects(), {}, {})

    for result in (leisure, physical):
        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "DEU_2027_OFFICIAL_SILGI_TOP12_RECORD_PRACTICAL"
        assert result["student_record_score"] == pytest.approx(300.0)
        assert result["used_subjects"] == 12
        assert result["minimum_csat"]["has_minimum"] is False
        assert result["vs_prev_year"]["practical_max"] == pytest.approx(700.0)


@_skip_no_db
def test_calculate_score_deu_school_life_tracks_are_official_noncalc() -> None:
    for uid in ("180", "181"):
        result = calculate_score(uid, _subjects(), {}, {})
        assert result["status"] == "non_calculation_track"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == "DEU_2027_SCHOOL_LIFE_HOLISTIC_NON_CALCULATION"
        assert result["minimum_csat"]["has_minimum"] is False
