from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

FORMULA_KEY = "HUFS_2027_RECOMMENDATION_RECORD1000"
HUFS_MINIMUM = "국어, 수학, 영어, 탐구(사회 또는 과학탐구 1과목) 중 2개 영역 등급 합 6 이내"
KNUE_MINIMUM = "국,수,영,탐(2) 중 4합 14이내"


def _perfect_subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for grade, semester in [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1)]:
        for group in ["국어", "수학", "영어", "사회", "과학", "한국사"]:
            rows.append(
                {
                    "학년": grade,
                    "학기": semester,
                    "교과": group,
                    "과목": f"{group}{grade}{semester}",
                    "이수단위": 2,
                    "등급": "1",
                    "원점수": 100,
                }
            )
    rows.append({"학년": 3, "학기": 1, "교과": "국어", "과목": "진로A", "이수단위": 2, "성취도": "A"})
    return rows


@_skip_no_db
def test_calculate_score_hufs_recommendation_uses_official_formula() -> None:
    result = calculate_score("376", _perfect_subjects(), {}, {})
    violence = calculate_score("376", _perfect_subjects(), {"school_violence_measure": 1}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == FORMULA_KEY
    assert result["student_record_score"] == pytest.approx(1000.0)
    assert result["record_full_score"] == pytest.approx(1000.0)
    assert result["practical_full_score"] == pytest.approx(0.0)
    assert result["minimum_csat"] == {"has_minimum": True, "detail": HUFS_MINIMUM}
    assert violence["status"] == "school_violence_ineligible"
    assert violence["formula_key"] == FORMULA_KEY


@_skip_no_db
def test_calculate_score_non_calculation_minimum_contracts() -> None:
    chungnam = calculate_score("370", _perfect_subjects(), {}, {})
    knue = calculate_score("371", _perfect_subjects(), {}, {})
    hufs_equity = calculate_score("372", _perfect_subjects(), {}, {})
    hufs_essay = calculate_score("373", _perfect_subjects(), {}, {})
    hufs_interview = calculate_score("374", _perfect_subjects(), {}, {})
    hufs_document = calculate_score("375", _perfect_subjects(), {}, {})

    assert chungnam["status"] == "non_calculation_track"
    assert chungnam["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
    assert knue["status"] == "non_calculation_track"
    assert knue["minimum_csat"] == {"has_minimum": True, "detail": KNUE_MINIMUM}
    assert hufs_equity["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
    assert hufs_essay["minimum_csat"] == {"has_minimum": True, "detail": HUFS_MINIMUM}
    assert hufs_interview["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
    assert hufs_document["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
