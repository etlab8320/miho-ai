from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")

HANNAM_KEY = "HANNAM_2027_SPORTS_PRACTICAL_RECORD400_PRACTICAL600"
HANSHIN_KEY = "HANSHIN_2027_PE_RECORD450_PRACTICAL550"
HANBAT_KEY = "HANBAT_2027_BIGDATA_HEALTHCARE_RECORD545"
KIU_COMPETITION_KEY = "KIU_2027_RECORD72_ATTENDANCE8_COMPETITION320"


def _hannam_subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    groups = ["국어", "수학", "영어", "사회", "과학"] * 2
    semesters = [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1)] * 2
    for index, (group, term) in enumerate(zip(groups, semesters)):
        rows.append(
            {
                "학년": term[0],
                "학기": term[1],
                "교과": group,
                "과목": f"{group}{index + 1}",
                "이수단위": 2,
                "등급": "1",
            }
        )
    return rows


def _hanshin_subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    groups = ["국어", "영어", "수학", "사회", "과학"]
    terms = [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1)]
    for index in range(12):
        grade, semester = terms[index % len(terms)]
        rows.append(
            {
                "학년": grade,
                "학기": semester,
                "교과": groups[index % len(groups)],
                "과목": f"과목{index + 1}",
                "이수단위": 1,
                "등급": "1",
            }
        )
    return rows


def _hanbat_subjects() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group, count in [("국어", 3), ("영어", 3), ("수학", 3), ("사회", 2), ("과학", 2)]:
        for index in range(count):
            rows.append(
                {
                    "학년": 1 + (index // 2),
                    "학기": 1 + (index % 2),
                    "교과": group,
                    "과목": f"{group}{index + 1}",
                    "이수단위": 8,
                    "등급": "1",
                }
            )
    rows.extend(
        [
            {"학년": 2, "학기": 1, "교과": "국어", "과목": "진로A", "이수단위": 8, "성취도": "A"},
            {"학년": 2, "학기": 1, "교과": "영어", "과목": "진로B", "이수단위": 8, "성취도": "A"},
            {"학년": 2, "학기": 1, "교과": "수학", "과목": "진로C", "이수단위": 8, "성취도": "A"},
        ]
    )
    return rows


@_skip_no_db
def test_calculate_score_hannam_uses_official_formula_plugin() -> None:
    result = calculate_score("383", _hannam_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == HANNAM_KEY
    assert result["student_record_score"] == pytest.approx(400.0)
    assert result["record_full_score"] == pytest.approx(400.0)
    assert result["practical_full_score"] == pytest.approx(600.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_hanshin_uses_official_formula_plugin() -> None:
    result = calculate_score("389", _hanshin_subjects(), {}, {})

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == HANSHIN_KEY
    assert result["student_record_score"] == pytest.approx(450.0)
    assert result["record_full_score"] == pytest.approx(450.0)
    assert result["practical_full_score"] == pytest.approx(550.0)
    assert result["full_practical_total"] == pytest.approx(1000.0)
    assert result["used_subjects"] == 12
    assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_hanbat_course_tracks_use_official_formula_plugin() -> None:
    for uid in ["390", "392"]:
        result = calculate_score(uid, _hanbat_subjects(), {}, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == HANBAT_KEY
        assert result["student_record_score"] == pytest.approx(545.0)
        assert result["record_full_score"] == pytest.approx(545.0)
        assert result["practical_full_score"] == pytest.approx(0.0)
        assert result["full_practical_total"] == pytest.approx(545.0)
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_remaining_non_calculation_tracks_have_no_minimum() -> None:
    for uid in ["391", "393", "394", "395", "396"]:
        result = calculate_score(uid, _hanbat_subjects(), {}, {})

        assert result["status"] == "non_calculation_track"
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}


@_skip_no_db
def test_calculate_score_kiu_competition_tracks_have_boolean_no_minimum() -> None:
    for uid in ["398", "399"]:
        result = calculate_score(uid, _hanbat_subjects(), {}, {})

        assert result["status"] == "calculated"
        assert result["strategy"] == "official_formula_plugin"
        assert result["formula_key"] == KIU_COMPETITION_KEY
        assert result["minimum_csat"] == {"has_minimum": False, "detail": "없음"}
