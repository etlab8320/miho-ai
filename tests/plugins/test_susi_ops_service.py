"""Tests for plugins.susi_ops.service — lookup roundtrip, unverified refusal, known calculation."""

from __future__ import annotations

import os

import pytest

from plugins.susi_ops.service import (
    _grade_value,
    _json_loads,
    _like,
    _norm_subject_area,
    _first_number,
    _score_from_grade_table,
    _subject_allowed,
    _unit_value,
    _weighted_average_grade,
    calculate_score,
    db_path,
    lookup_rules,
)
from plugins.susi_ops.score_adjustments import (
    achievement_ratio_grade,
    apply_unit_shortfall_adjustment,
)
from plugins.susi_ops.semester_rules import within_semester_limit

_DB_AVAILABLE = db_path().exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="susi27 staging DB not present")


# ---------------------------------------------------------------------------
# Pure unit tests — no DB required
# ---------------------------------------------------------------------------


def test_like_wraps_in_percent() -> None:
    assert _like("국민대") == "%국민대%"


def test_like_none_becomes_empty_wildcard() -> None:
    assert _like(None) == "%%"


def test_json_loads_valid() -> None:
    assert _json_loads('{"a": 1}', {}) == {"a": 1}


def test_json_loads_empty_returns_default() -> None:
    assert _json_loads(None, {"x": 1}) == {"x": 1}


def test_json_loads_invalid_returns_default() -> None:
    assert _json_loads("{bad json}", []) == []


def test_norm_subject_area_alias() -> None:
    assert _norm_subject_area("국") == "국어"
    assert _norm_subject_area("수") == "수학"
    assert _norm_subject_area("영") == "영어"
    assert _norm_subject_area("사") == "사회"
    assert _norm_subject_area("과") == "과학"


def test_norm_subject_area_passthrough() -> None:
    assert _norm_subject_area("국어") == "국어"
    assert _norm_subject_area("기타") == "기타"


def test_grade_value_grade_key() -> None:
    assert _grade_value({"grade": "3"}) == 3.0


def test_grade_value_hangul_key() -> None:
    assert _grade_value({"등급": "2"}) == 2.0


def test_grade_value_missing_returns_none() -> None:
    assert _grade_value({"subject": "국어"}) is None


def test_unit_value_hangul_key() -> None:
    assert _unit_value({"이수단위": "4"}) == 4.0


def test_unit_value_zero_falls_back_to_one() -> None:
    assert _unit_value({"unit": "0"}) == 1.0


def test_unit_value_missing_returns_one() -> None:
    assert _unit_value({}) == 1.0


def test_subject_allowed_no_area_returns_true() -> None:
    assert _subject_allowed({}, {"국어": "O"}) is True


def test_subject_allowed_matching_flag() -> None:
    row = {"area": "국어"}
    assert _subject_allowed(row, {"국어": "O"}) is True


def test_subject_allowed_flag_off() -> None:
    row = {"area": "수학"}
    assert _subject_allowed(row, {"수학": "", "국어": "O"}) is False


def test_subject_allowed_fallback_to_etc() -> None:
    row = {"area": "기술"}
    assert _subject_allowed(row, {"기타": "O"}) is True


def test_weighted_average_grade_basic() -> None:
    grades = [
        {"교과": "국어", "grade": "1", "unit": "4"},
        {"교과": "국어", "grade": "3", "unit": "4"},
    ]
    score_logic = {"subject_flags": {"국어": "O"}, "regular_subjects": ""}
    avg, used, total, _ = _weighted_average_grade(grades, score_logic)
    assert avg == pytest.approx(2.0)
    assert used == 2
    assert total == pytest.approx(8.0)


def test_weighted_average_grade_empty_grades_returns_none() -> None:
    avg, used, total, _ = _weighted_average_grade([], {"subject_flags": {}})
    assert avg is None
    assert used == 0


def test_semester_limit_expected_graduate_stops_at_third_grade_first_semester() -> None:
    row = {"학년": 3, "학기": 2}
    limit = "졸업예정자: 1학년 1학기~3학년 1학기; 졸업자: 전학년"

    assert within_semester_limit(row, limit, {"graduation_status": "expected"}) is False


def test_semester_limit_graduate_allows_full_years_when_pdf_rule_says_so() -> None:
    row = {"학년": 3, "학기": 2}
    limit = "졸업예정자: 1학년 1학기~3학년 1학기; 졸업자: 전학년"

    assert within_semester_limit(row, limit, {"graduation_status": "graduate"}) is True


def test_score_from_grade_table_exact_hit() -> None:
    gp = {"1": "300.0", "2": "298.5", "9": "90.0"}
    assert _score_from_grade_table(1.0, gp) == pytest.approx(300.0)


def test_score_from_grade_table_interpolation() -> None:
    gp = {"1": "300.0", "2": "298.5"}
    # avg 1.75 → 300 + (298.5 - 300) * 0.75
    result = _score_from_grade_table(1.75, gp)
    assert result == pytest.approx(298.875)


def test_score_from_grade_table_clamp_max() -> None:
    gp = {"1": "300.0", "9": "90.0"}
    # 0.5 is below min(1) → clamp to points[1]
    assert _score_from_grade_table(0.5, gp) == pytest.approx(300.0)


def test_score_from_grade_table_clamp_min() -> None:
    gp = {"1": "300.0", "9": "90.0"}
    # 9.5 is above max(9) → clamp to points[9]
    assert _score_from_grade_table(9.5, gp) == pytest.approx(90.0)


def test_score_from_grade_table_empty_returns_none() -> None:
    assert _score_from_grade_table(3.0, {}) is None


def test_first_number_preserves_zero_float() -> None:
    assert _first_number(0.0) == pytest.approx(0.0)


def test_unit_shortfall_adjustment_applies_pdf_factor() -> None:
    score_logic = {
        "unit_shortfall_adjustment": {
            "threshold_units": 70,
            "base_factor": 0.96,
            "per_missing_unit": 0.002,
        }
    }

    adjusted = apply_unit_shortfall_adjustment(200.0, 65.0, score_logic)

    assert adjusted == pytest.approx(200.0 * (0.96 - 5 * 0.002))


def test_unit_shortfall_adjustment_ignores_sufficient_units() -> None:
    score_logic = {"unit_shortfall_adjustment": {"threshold_units": 70}}

    assert apply_unit_shortfall_adjustment(200.0, 70.0, score_logic) == pytest.approx(200.0)


def test_achievement_ratio_grade_requires_ratio_for_b_or_c() -> None:
    assert achievement_ratio_grade({"achievement": "C"}, "C") is None


def test_achievement_ratio_grade_maps_konkuk_ratio_table() -> None:
    row = {"achievement_ratios": {"B": 22.0, "C": 5.0}}

    assert achievement_ratio_grade(row, "A") == pytest.approx(1.0)
    assert achievement_ratio_grade(row, "B") == pytest.approx(6.0)
    assert achievement_ratio_grade(row, "C") == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# DB-dependent tests
# ---------------------------------------------------------------------------


@_skip_no_db
def test_lookup_roundtrip_returns_dict_with_rows() -> None:
    result = lookup_rules(university="가천대", limit=5)

    assert isinstance(result, dict)
    assert "db_path" in result
    assert "count" in result
    assert "rows" in result
    assert result["count"] >= 1

    row = result["rows"][0]
    assert row["university"].startswith("가천대")
    assert "university_id" in row
    assert "confidence" in row
    # 요약 모드(기본): 엔진 내부 룰은 컨텍스트에 싣지 않는다
    assert "score_logic" not in row
    assert "admission_meta" in row
    assert "admission_result_26" in row

    detailed = lookup_rules(university="가천대", limit=1, detail=True)
    drow = detailed["rows"][0]
    assert "score_logic" in drow
    assert "queue_status" in drow
    assert "db_snapshot" in drow


@_skip_no_db
def test_lookup_no_match_returns_empty_rows() -> None:
    result = lookup_rules(university="존재하지않는대학XYZ")
    assert result["count"] == 0
    assert result["rows"] == []


@_skip_no_db
def test_calculate_score_missing_rule_refused() -> None:
    result = calculate_score(
        university_id="999999999",
        grades=[],
        attendance={},
        practical_records={},
    )
    assert result["status"] == "missing_rule"
    assert "university_id" in result


@_skip_no_db
def test_calculate_score_unverified_rule_refused() -> None:
    # Find an unverified row from the DB
    import sqlite3

    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    # 공식 formula_key가 있는 행은 confidence 라벨이 plugin_ready/non_calculation_track이어도
    # 플러그인 자체 검증 상태를 우선한다. 이 테스트는 실행기 없는 미검증 행만 거부 확인한다.
    row = conn.execute(
        "SELECT university_id FROM susi_calculation_rules "
        "WHERE json_extract(score_logic_json, '$.formula_key') IS NULL "
        "AND (confidence NOT LIKE '%verified%' OR confidence LIKE '%non_calc%') "
        "AND coalesce(json_extract(score_logic_json, '$.calculation_readiness'), '') NOT LIKE '%non_calculation_track%' "
        "AND coalesce(json_extract(score_logic_json, '$.calculation_scope'), '') NOT LIKE '%non_calculation_track%' "
        "AND coalesce(json_extract(score_logic_json, '$.calculation_readiness'), '') != 'not_in_2027_official_guide' "
        "AND coalesce(json_extract(score_logic_json, '$.calculation_scope'), '') != 'not_in_2027_official_guide' "
        "LIMIT 1"
    ).fetchone()
    conn.close()

    if row is None:
        pytest.skip("no unverified rows in test DB")

    result = calculate_score(
        university_id=row["university_id"],
        grades=[{"grade": "1", "unit": "4", "교과": "국어"}],
        attendance={},
        practical_records={},
    )
    assert result["status"] == "unverified_rule"
    assert result.get("confidence") != "verified"


@_skip_no_db
def test_calculate_score_known_case_gachon() -> None:
    """가천대(university_id=1) verified rule. 국어/영어 O, grade_points 1→300.

    grades: 국어 grade-1 4단위, 국어 grade-2 4단위, 영어 grade-1 4단위, 영어 grade-3 4단위.
    expected avg = 1.75, student_record_score ≈ 298.875.
    """
    grades = [
        {"교과": "국어", "grade": "1", "unit": "4"},
        {"교과": "국어", "grade": "2", "unit": "4"},
        {"교과": "영어", "grade": "1", "unit": "4"},
        {"교과": "영어", "grade": "3", "unit": "4"},
    ]
    result = calculate_score(
        university_id="1",
        grades=grades,
        attendance={},
        practical_records={},
    )
    assert result["status"] == "calculated"
    assert result["confidence"] == "verified"
    assert result["average_grade"] == pytest.approx(1.75, abs=0.001)
    assert result["student_record_score"] == pytest.approx(298.875, abs=0.001)
    assert result["used_subjects"] == 4


@_skip_no_db
def test_calculate_score_kangwon_uses_official_formula_plugin() -> None:
    grades = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "체육", "과목": "체육", "이수단위": 3, "등급": "1"},
    ]

    result = calculate_score(
        university_id="7",
        grades=grades,
        attendance={},
        practical_records={},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(1000.0)


@_skip_no_db
def test_calculate_score_konkuk_glocal_requires_career_ratio_inputs() -> None:
    grades = [
        {"학년": 3, "학기": 1, "교과": "국어", "과목": "심화 국어", "이수단위": 2, "성취도": "C", "course_type": "진로선택"},
        {"학년": 3, "학기": 1, "교과": "영어", "과목": "진로 영어", "이수단위": 2, "성취도": "C", "course_type": "진로선택"},
        {"학년": 3, "학기": 1, "교과": "한국사", "과목": "한국사", "이수단위": 3, "등급": "2"},
    ]

    result = calculate_score(
        university_id="9",
        grades=grades,
        attendance={},
        practical_records={},
    )

    assert result["status"] == "missing_career_ratio_inputs"
    assert result["missing_subjects"][0]["subject"] == "심화 국어"


@_skip_no_db
def test_calculate_score_gyeongguk_uses_official_formula_with_attendance() -> None:
    grades = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": "1"},
    ]

    result = calculate_score(
        university_id="15",
        grades=grades,
        attendance={"unexcused_absence_days": 3},
        practical_records={},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(397.0)


@_skip_no_db
def test_calculate_score_kyonggi_uses_official_formula_plugin() -> None:
    grades = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학", "이수단위": 3, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "통합사회", "이수단위": 3, "등급": "1"},
    ]

    result = calculate_score(
        university_id="16",
        grades=grades,
        attendance={},
        practical_records={},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(30.0)


@_skip_no_db
def test_calculate_score_kyonggi_graduate_includes_third_grade_second_semester() -> None:
    grades = [
        {"학년": 3, "학기": 2, "교과": "국어", "과목": "고전 읽기", "이수단위": 3, "등급": "1"},
        {"학년": 3, "학기": 2, "교과": "영어", "과목": "진로 영어", "이수단위": 3, "등급": "1"},
    ]

    result = calculate_score(
        university_id="16",
        grades=grades,
        attendance={},
        practical_records={},
        student_context={"graduation_status": "graduate"},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["student_record_score"] == pytest.approx(30.0)


@_skip_no_db
def test_calculate_score_kyungnam_student_comprehensive_stays_non_calculation() -> None:
    result = calculate_score(
        university_id="20",
        grades=[{"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"}],
        attendance={},
        practical_records={},
    )

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"


@_skip_no_db
def test_calculate_score_knu_plugin_ready_formula_is_allowed() -> None:
    result = calculate_score(
        university_id="22",
        grades=[
            {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"},
            {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어", "이수단위": 3, "등급": "1"},
        ],
        attendance={},
        practical_records={},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KNU_2027_STUDENT_COURSE400_COMPLETION_REVIEW100"
    assert result["student_record_score"] == pytest.approx(400.0)


@_skip_no_db
def test_calculate_score_knu_non_calculation_formula_is_allowed() -> None:
    result = calculate_score(
        university_id="24",
        grades=[{"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"}],
        attendance={},
        practical_records={},
    )

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KNU_2027_STUDENT_RECORD_DOCUMENT_REVIEW_100"


@_skip_no_db
def test_calculate_score_kyungsung_practical_uses_official_formula_plugin() -> None:
    grades = [
        {"학년": 1, "학기": 1, "교과": "국어", "과목": "국어1", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "국어", "과목": "국어2", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "수학", "과목": "수학1", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "수학", "과목": "수학2", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "영어", "과목": "영어1", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "영어", "과목": "영어2", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "사회", "과목": "사회1", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "사회", "과목": "사회2", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 1, "교과": "기타", "과목": "기타1", "이수단위": 1, "등급": "1"},
        {"학년": 1, "학기": 2, "교과": "기타", "과목": "기타2", "이수단위": 1, "등급": "1"},
    ]

    result = calculate_score(
        university_id="38",
        grades=grades,
        attendance={},
        practical_records={},
    )

    assert result["status"] == "calculated"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KYUNGSUNG_2027_OFFICIAL_SPORTS_HEALTH_RECORD100_PRACTICAL900"
    assert result["student_record_score"] == pytest.approx(100.0)


@_skip_no_db
def test_calculate_score_kyungsung_student_comprehensive_stays_non_calculation() -> None:
    result = calculate_score(
        university_id="39",
        grades=[{"학년": 1, "학기": 1, "교과": "국어", "과목": "국어", "이수단위": 3, "등급": "1"}],
        attendance={},
        practical_records={},
    )

    assert result["status"] == "non_calculation_track"
    assert result["strategy"] == "official_formula_plugin"
    assert result["formula_key"] == "KYUNGSUNG_2027_STUDENT_RECORD_COMPREHENSIVE_NON_CALCULATION"


# ---------------------------------------------------------------------------
# lookup_prev_year (26susi 크로스체크)
# ---------------------------------------------------------------------------

def test_prev_year_requires_search_term():
    from plugins.susi_ops.service import lookup_prev_year

    assert "error" in lookup_prev_year()


def test_prev_year_sanitizes_terms():
    from plugins.susi_ops.service import _safe_like_term

    assert _safe_like_term("중부'; DROP TABLE x; --") == "중부 DROP TABLE x --"
    assert _safe_like_term('대진"`\\') == "대진"
    assert _safe_like_term(None) is None


def test_prev_year_parses_rows(monkeypatch):
    from plugins.susi_ops import service

    calls = []

    def fake_mysql(sql, timeout=12):
        calls.append(sql)
        if "대학정보" in sql:
            return [["334", "96", "중부대학교", "스포츠건강관리학전공", "실기우수자", "12",
                     "NULL", "NULL", "30", "70", "NULL", "NULL", "700", "100"]]
        return [["96", "10m왕복달리기"], ["96", "서전트점프"]]

    monkeypatch.setattr(service, "_vultr_mysql", fake_mysql)
    result = service.lookup_prev_year(university="중부")
    assert result["count"] == 1
    row = result["rows"][0]
    assert row["stage2_record"] == "30" and row["stage2_practical"] == "70"
    assert row["practical_events_prev"] == ["10m왕복달리기", "서전트점프"]
    assert len(calls) == 2


def test_recommend_candidates_missing_student(monkeypatch, tmp_path):
    from plugins.susi_ops import service

    monkeypatch.setattr(service, "_CENTRAL_LIFE_DB", tmp_path / "none.sqlite3")
    assert "error" in service.recommend_candidates("없는학생", region="전국")


def test_recommend_candidates_filters_unreachable(monkeypatch):
    from plugins.susi_ops import service

    monkeypatch.setattr(service, "_student_grades_from_central", lambda q: ("백종환", [{"교과": "국어", "과목": "국어", "이수단위": 4, "등급": "7"}]))

    class FakeRow(dict):
        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    rules = [FakeRow(university_id="u1", university="가능대", department="체육", admission_track="실기",
                     practical_events_json=None, calculation_test_json=None,
                     raw_json='{"정원": "10", "내신교과": "200", "실기만점": "800"}'),
             FakeRow(university_id="u2", university="불가대", department="체육", admission_track="실기",
                     practical_events_json=None, calculation_test_json=None,
                     raw_json='{"정원": "5", "내신교과": "200", "실기만점": "600"}')]

    class FakeConn:
        def execute(self, sql, params=()):
            class C:
                def fetchall(self_inner):
                    return rules
                def fetchone(self_inner):
                    return ['{"final_pass_cutoff": {"total_score": 900.0, "record_score": 150.0}}', "{}"]
            return C()

    monkeypatch.setattr(service, "_connect", lambda: FakeConn())

    def fake_calc(uid, grades, att, prac):
        base = {"status": "calculated", "student_record_score": 160.0}
        if uid == "u1":
            base["vs_prev_year"] = {"practical_max": 800.0, "max_possible_total": 960.0,
                                    "prev_final_total": 900.0, "prev_first_total": None,
                                    "prev_final_record_rescaled": 150.0,
                                    "reachable_at_full_practical": True}
        else:
            base["vs_prev_year"] = {"practical_max": 600.0, "max_possible_total": 760.0,
                                    "prev_final_total": 900.0, "prev_first_total": None,
                                    "prev_final_record_rescaled": 150.0,
                                    "reachable_at_full_practical": False}
        return base

    monkeypatch.setattr(service, "calculate_score", fake_calc)
    result = service.recommend_candidates("백종환", region="전국")
    names = [c["university"] for c in result["candidates"]]
    assert "가능대" in names and "불가대" not in names
    assert result["skipped"]["unreachable"] == 1
    assert result["candidates"][0]["suggested_verdict"] == "적정"


def test_recommend_candidates_requires_region():
    from plugins.susi_ops import service

    result = service.recommend_candidates("아무개")
    assert result.get("need_region") is True
    assert "지역" in result.get("message", "")


def test_recommend_handler_same_turn_region_recall_allowed(monkeypatch):
    """현관 게이트 도입 후: 지역을 받은 턴의 재호출은 정상 통과해야 한다."""
    from plugins import susi_ops

    monkeypatch.setattr(susi_ops, "recommend_candidates", lambda **kw: {"need_region": True} if not kw.get("region") else {"total_feasible": 1, "candidates": []})

    first = susi_ops._recommend_handler({"student_query": "서연"})
    assert first.get("need_region") is True
    second = susi_ops._recommend_handler({"student_query": "서연", "region": "서울, 경기, 인천, 강원, 충청"})
    assert second.get("total_feasible") == 1
