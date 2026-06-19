from __future__ import annotations

import pytest

from plugins.susi_ops.service import calculate_score, db_path
from plugins.susi_ops.rules import lookup_rules


_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


def _graduate_subjects() -> list[dict[str, object]]:
    groups = ["국어", "영어", "수학", "사회", "과학"]
    rows = []
    for index, grade in enumerate(["1"] * 11 + ["9"]):
        rows.append({
            "학년": 1 + index // 5 if index < 10 else 3,
            "학기": 1,
            "교과": groups[index % len(groups)],
            "과목": f"과목{index}",
            "이수단위": 1,
            "등급": grade,
        })
    rows.append({"학년": 3, "학기": 2, "교과": "국어", "과목": "졸업자3-2고점", "이수단위": 1, "등급": "1"})
    return rows


@_skip_no_db
def test_calculate_score_hanshin_graduate_context_includes_grade3_semester2() -> None:
    current = calculate_score("389", _graduate_subjects(), {}, {}, {"is_graduate": False})
    graduate = calculate_score("389", _graduate_subjects(), {}, {}, {"is_graduate": True})

    assert current["status"] == "calculated"
    assert current["student_record_score"] == pytest.approx(431.2485)
    assert graduate["status"] == "calculated"
    assert graduate["student_record_score"] == pytest.approx(450.0)
    assert graduate["full_practical_total"] == pytest.approx(1000.0)


@_skip_no_db
def test_lookup_rules_hanshin_stage_meta_matches_official_45_55() -> None:
    rows = lookup_rules(university="한신대학교", department="특수체육", detail=True)["rows"]
    row = next(item for item in rows if item["university_id"] == "389")

    assert row["admission_meta"]["stage2"]["student_record"] == "45"
    assert row["admission_meta"]["stage2"]["practical"] == "55"
