"""Recommendation entrypoint contract tests for plugins.susi_ops."""

from __future__ import annotations

from typing import Any


def test_recommend_handler_uses_single_recommendation_pipeline(monkeypatch) -> None:
    from plugins import susi_ops

    calls: list[dict[str, Any]] = []

    def fake_recommend_candidates(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"sentinel": "single_pipeline", "candidates": []}

    monkeypatch.setattr(susi_ops, "recommend_candidates", fake_recommend_candidates)

    result = susi_ops._recommend_handler(
        {
            "student_query": "박시현",
            "university": "경기대",
            "department": "체육",
            "admission_track": "실기",
            "region": "경기",
            "max_candidates": 7,
        }
    )

    assert result == {"sentinel": "single_pipeline", "candidates": []}
    assert calls == [
        {
            "student_query": "박시현",
            "university": "경기대",
            "department": "체육",
            "admission_track": "실기",
            "region": "경기",
            "max_candidates": 7,
            "student_gender": None,
        }
    ]


def test_recommend_tool_description_forces_single_pipeline() -> None:
    from plugins import susi_ops

    class Ctx:
        def __init__(self) -> None:
            self.tools: dict[str, dict[str, Any]] = {}

        def register_tool(self, name: str, **kwargs: Any) -> None:
            self.tools[name] = kwargs

    ctx = Ctx()
    susi_ops.register(ctx)

    desc = ctx.tools["susi27_recommend_candidates"]["description"]
    assert "수시 실기/교과 추천의 시작점" in desc
    assert "룰/계산 도구를 따로 조립하지 말고" in desc
    assert "이걸 먼저 호출" in desc
    rule_desc = ctx.tools["susi27_rule_lookup"]["description"]
    score_desc = ctx.tools["susi27_score_calculate"]["description"]
    assert "추천은 반드시 susi27_recommend_candidates" in rule_desc
    assert "후보를 조립하지 마라" in score_desc


def test_prev_year_requires_search_term() -> None:
    from plugins.susi_ops.prev_year import lookup_prev_year

    assert "error" in lookup_prev_year()


def test_prev_year_sanitizes_terms() -> None:
    from plugins.susi_ops.prev_year import _safe_like_term

    assert _safe_like_term("중부'; DROP TABLE x; --") == "중부 DROP TABLE x --"
    assert _safe_like_term('대진"`\\') == "대진"
    assert _safe_like_term(None) is None


def test_prev_year_parses_rows(monkeypatch) -> None:
    from plugins.susi_ops import prev_year

    calls = []

    def fake_mysql(sql: str, timeout: int = 12) -> list[list[str]]:
        calls.append(sql)
        if "대학정보" in sql:
            return [
                [
                    "334",
                    "96",
                    "중부대학교",
                    "스포츠건강관리학전공",
                    "실기우수자",
                    "12",
                    "NULL",
                    "NULL",
                    "30",
                    "70",
                    "NULL",
                    "NULL",
                    "700",
                    "100",
                ]
            ]
        return [["96", "10m왕복달리기"], ["96", "서전트점프"]]

    monkeypatch.setattr(prev_year, "_vultr_mysql", fake_mysql)

    result = prev_year.lookup_prev_year(university="중부")

    assert result["count"] == 1
    row = result["rows"][0]
    assert row["stage2_record"] == "30" and row["stage2_practical"] == "70"
    assert row["practical_events_prev"] == ["10m왕복달리기", "서전트점프"]
    assert len(calls) == 2


def test_recommend_candidates_missing_student(monkeypatch, tmp_path) -> None:
    from plugins.susi_ops import recommendation

    monkeypatch.setattr(recommendation, "_CENTRAL_LIFE_DB", tmp_path / "none.sqlite3")

    assert "error" in recommendation.recommend_candidates("없는학생", region="전국")


def test_region_map_initializes_without_cached_file(monkeypatch, tmp_path) -> None:
    from plugins.susi_ops import recommendation

    monkeypatch.setattr(recommendation, "_REGION_MAP", None)
    monkeypatch.setattr(recommendation, "_REGION_MAP_PATH", tmp_path / "missing" / "region.json")
    monkeypatch.setattr(recommendation, "_vultr_mysql", lambda sql: [])

    assert recommendation._region_map() == {}


def test_recommend_candidates_filters_unreachable(monkeypatch) -> None:
    from plugins.susi_ops import recommendation

    monkeypatch.setattr(
        recommendation,
        "_student_grades_from_central",
        lambda q: ("백종환", [{"교과": "국어", "과목": "국어", "이수단위": 4, "등급": "7"}]),
    )
    monkeypatch.setattr(recommendation, "_region_map", lambda: {"u1": "경기", "u2": "경기"})

    class FakeRow(dict):
        def __getitem__(self, key: str) -> Any:
            return dict.__getitem__(self, key)

    rules = [
        FakeRow(
            university_id="u1",
            university="가능대",
            department="체육",
            admission_track="실기",
            practical_events_json=(
                '{"events":[{"name":"스포츠분야 분석 및 질의응답"}],'
                '"stage1_events":[{"name":"제자리멀리뛰기"},{"name":"메디신볼던지기"},'
                '{"name":"10m왕복달리기"},{"name":"좌전굴"}],'
                '"selection_rule":"1단계 과목측정은 400% 선발용, 2단계는 스포츠분야 분석 및 질의응답 800점"}'
            ),
            calculation_test_json=None,
            raw_json='{"정원": "10", "내신교과": "200", "실기만점": "800"}',
        ),
        FakeRow(
            university_id="u2",
            university="불가대",
            department="체육",
            admission_track="실기",
            practical_events_json=None,
            calculation_test_json=None,
            raw_json='{"정원": "5", "내신교과": "200", "실기만점": "600"}',
        ),
    ]

    class FakeConn:
        def execute(self, sql: str, params: tuple[Any, ...] = ()):
            class Cursor:
                def fetchall(self_inner) -> list[FakeRow]:
                    return rules

                def fetchone(self_inner) -> list[str]:
                    return [
                        '{"final_pass_cutoff": {"total_score": 900.0, "record_score": 150.0}}',
                        '{"minimum_csat": {"has_minimum": true, "detail": "상위 2개 영역 합 6등급 이내"}}',
                    ]

            return Cursor()

    monkeypatch.setattr(recommendation, "_connect", lambda: FakeConn())
    monkeypatch.setattr(
        recommendation,
        "_track_cuts",
        lambda uid: (
            {"final_cut_total": 800.0, "events": ["기초체력"], "n_students": 4},
            [
                {"final_cut_total": 800.0, "events": ["기초체력"], "n_students": 4},
                {"final_cut_total": 920.0, "events": ["전공실기"], "n_students": 4},
            ],
        ) if uid == "u1" else (None, []),
    )

    def fake_calc(uid: str, grades: list[dict[str, Any]], att: dict[str, Any], prac: dict[str, Any]) -> dict[str, Any]:
        base: dict[str, Any] = {"status": "calculated", "student_record_score": 160.0}
        if uid == "u1":
            base["vs_prev_year"] = {
                "practical_max": 800.0,
                "max_possible_total": 960.0,
                "prev_final_total": 900.0,
                "prev_first_total": None,
                "prev_final_record_rescaled": 150.0,
                "reachable_at_full_practical": True,
            }
        else:
            base["vs_prev_year"] = {
                "practical_max": 600.0,
                "max_possible_total": 760.0,
                "prev_final_total": 900.0,
                "prev_first_total": None,
                "prev_final_record_rescaled": 150.0,
                "reachable_at_full_practical": False,
            }
        return base

    monkeypatch.setattr(recommendation, "calculate_score", fake_calc)

    result = recommendation.recommend_candidates("백종환", region="전국")

    names = [c["university"] for c in result["candidates"]]
    assert "가능대" in names and "불가대" not in names
    assert result["skipped"]["unreachable"] == 1
    assert result["candidates"][0]["prev_final_total"] == 800.0
    assert "기초체력" in result["candidates"][0]["track_note"]
    assert result["candidates"][0]["suggested_verdict"] == "적정"
    assert result["candidates"][0]["practical_events"][0].startswith("1단계:")
    assert result["candidates"][0]["practical_events"][1] == "2단계: 스포츠분야 분석·질의응답"
    assert "실기 100%" in result["candidates"][0]["practical_event_note"]
    assert result["candidates"][0]["minimum_csat"] == "상위 2개 영역 합 6등급 이내"


def test_recommend_candidates_requires_region() -> None:
    from plugins.susi_ops.recommendation import recommend_candidates

    result = recommend_candidates("아무개")
    assert result.get("need_region") is True
    assert "지역" in result.get("message", "")


def test_recommend_candidates_does_not_filter_generic_practical_category(monkeypatch) -> None:
    from plugins.susi_ops import recommendation

    captured: dict[str, Any] = {}

    class FakeConn:
        def execute(self, sql: str, params: list[Any]):
            captured["sql"] = sql
            captured["params"] = params

            class Cursor:
                def fetchall(self_inner) -> list[dict[str, Any]]:
                    return []

            return Cursor()

    monkeypatch.setattr(
        recommendation,
        "_student_grades_from_central",
        lambda q: ("홍예지", [{"교과": "국어", "과목": "국어", "이수단위": 4, "등급": "5"}]),
    )
    monkeypatch.setattr(recommendation, "_connect", lambda: FakeConn())

    for label in (
        "실기", "실기전형", "수시 실기", "전국 실기", "전체 실기", "실기 추천",
        "전국 실기 추천", "전국 실기전형 추천", "전체 실기 추천", "전국 수시 실기",
    ):
        recommendation.recommend_candidates("홍예지", region="전국", admission_track=label)
        assert "c.admission_track LIKE" not in captured["sql"]
        assert captured["params"] == []

    recommendation.recommend_candidates("홍예지", region="전국", admission_track="실기우수자")

    assert "c.admission_track LIKE" in captured["sql"]
    assert captured["params"] == ["%실기우수자%"]


def test_recommend_candidates_excludes_record_only_rows_for_practical_category(monkeypatch) -> None:
    from plugins.susi_ops import recommendation

    class FakeRow(dict):
        def __getitem__(self, key: str) -> Any:
            return dict.__getitem__(self, key)

    rules = [
        FakeRow(
            university_id="practical",
            university="실기대",
            department="체육학과",
            admission_track="학교장추천",
            confidence="verified",
            score_logic_json="{}",
            practical_events_json='{"events":[{"name":"제자리멀리뛰기"}]}',
            calculation_test_json='{"plugin_practical_full_score":800}',
            raw_json='{"정원": "10", "내신교과": "200", "실기만점": "800"}',
        ),
        FakeRow(
            university_id="record",
            university="교과대",
            department="체육학과",
            admission_track="학생부교과 일반",
            confidence="verified",
            score_logic_json="{}",
            practical_events_json=None,
            calculation_test_json='{"plugin_practical_full_score":0}',
            raw_json='{"정원": "5", "내신교과": "1000", "실기만점": "0"}',
        ),
    ]

    class FakeConn:
        def execute(self, sql: str, params: list[Any] | tuple[Any, ...] = ()):
            class Cursor:
                def fetchall(self_inner) -> list[FakeRow]:
                    return rules

                def fetchone(self_inner) -> list[str]:
                    return ['{"final_pass_cutoff": {"total_score": 900.0}}', "{}"]

            return Cursor()

    monkeypatch.setattr(
        recommendation,
        "_student_grades_from_central",
        lambda q: ("홍예지", [{"교과": "국어", "과목": "국어", "이수단위": 4, "등급": "5"}]),
    )
    monkeypatch.setattr(recommendation, "_connect", lambda: FakeConn())
    monkeypatch.setattr(recommendation, "_region_map", lambda: {"practical": "경기", "record": "경기"})
    monkeypatch.setattr(recommendation, "_track_cuts", lambda uid: (None, []))

    def fake_calc(uid: str, grades: list[dict[str, Any]], att: dict[str, Any], prac: dict[str, Any]) -> dict[str, Any]:
        assert uid == "practical"
        return {
            "status": "calculated",
            "student_record_score": 160.0,
            "vs_prev_year": {
                "practical_max": 800.0,
                "max_possible_total": 960.0,
                "prev_final_total": 900.0,
                "prev_first_total": None,
                "reachable_at_full_practical": True,
            },
        }

    monkeypatch.setattr(recommendation, "calculate_score", fake_calc)

    result = recommendation.recommend_candidates("홍예지", region="전국", admission_track="수시 실기")

    assert [candidate["university"] for candidate in result["candidates"]] == ["실기대"]
    assert result["skipped"]["non_practical"] == 1


def test_gender_filter_blocks_women_only_school_for_male_student() -> None:
    from plugins.susi_ops import recommendation

    assert recommendation._gender_key("남자") == "male"
    assert recommendation._gender_key("여자") == "female"
    assert recommendation._is_gender_ineligible("서울여자대학교", "sports", "male")
    assert not recommendation._is_gender_ineligible("서울여자대학교", "sports", "female")
    assert not recommendation._is_gender_ineligible("열린대학교", "sports", "male")


def test_practical_verdict_uses_needed_practical_rate() -> None:
    from plugins.susi_ops.recommendation_verdict import practical_verdict

    assert practical_verdict(0.0) == "적정"
    assert practical_verdict(85.0) == "적정"
    assert practical_verdict(85.1) == "상향"
    assert practical_verdict(99.0) == "상향"
    assert practical_verdict(90.9, margin_at_full_practical=54.51, practical_max=600.0) == "적정"
    assert practical_verdict(93.2, margin_at_full_practical=47.83, practical_max=700.0) == "적정"
    assert practical_verdict(94.8, margin_at_full_practical=41.47, practical_max=800.0) == "상향"


def test_recommend_candidates_treats_social_care_as_restricted_track() -> None:
    from plugins.susi_ops.recommendation import _is_restricted_record_only_track

    assert _is_restricted_record_only_track("사회배려")
    assert _is_restricted_record_only_track("농어촌전형")
    assert not _is_restricted_record_only_track("일반고교과")


def test_recommend_candidates_blocks_official_absent_rows() -> None:
    from plugins.susi_ops.recommendation import _is_blocked_official_row

    assert _is_blocked_official_row("official_pdf_absent_row_codex_verified", "{}")
    assert _is_blocked_official_row(
        "official_pdf_codex_verified",
        '{"calculation_readiness":"not_in_2027_official_guide"}',
    )
    assert _is_blocked_official_row(
        "official_pdf_codex_verified",
        '{"calculation_scope":"do_not_calculate_absent_row"}',
    )
    assert _is_blocked_official_row(
        "official_pdf_codex_verified",
        '{"calculation_readiness":"non_calculation_track_with_clear_reason"}',
    )
    assert not _is_blocked_official_row("official_pdf_codex_verified", "{}")


def test_recommend_candidates_filters_condition_limited_tracks_by_request() -> None:
    from plugins.susi_ops.recommendation import _is_allowed_recommendation_target, _is_specific_sport_practical_row

    assert not _is_allowed_recommendation_target("태권도학과", "실기우수자", None)
    assert not _is_allowed_recommendation_target("무도학과", "실기우수자", None)
    assert not _is_allowed_recommendation_target("시각디자인학과", "실기우수자", None)
    assert not _is_allowed_recommendation_target("연기예술학과", "실기우수자", None)
    assert not _is_allowed_recommendation_target("실용음악학과", "실기우수자", None)
    assert not _is_allowed_recommendation_target("빅데이터헬스케어융합학과", "학생부교과", None)
    assert _is_allowed_recommendation_target("경호학과", "실기우수자", None)
    assert _is_allowed_recommendation_target("무도경호학과", "실기우수자", None)
    assert _is_allowed_recommendation_target("스포츠재활학과", "실기우수자", None)
    assert not _is_allowed_recommendation_target("체육학과", "농어촌학생", None)
    assert not _is_allowed_recommendation_target("스포츠과학과", "기회균형", None)
    assert _is_allowed_recommendation_target("체육학과", "농어촌학생", "농어촌")
    assert _is_allowed_recommendation_target("스포츠과학과", "기회균형", "기균")
    assert _is_allowed_recommendation_target("체육학과", "실기우수자", None)
    assert _is_specific_sport_practical_row(
        '{"events":[{"name":"야구","selection_note":"포지션별 종목별 선발"}]}'
    )
    assert not _is_specific_sport_practical_row(
        '{"events":[{"name":"제자리 멀리뛰기"},{"name":"좌전굴"}],"selection_rule":"전 종목 반영"}'
    )


def test_recommend_candidates_displays_branch_campuses_without_seoul_tier(monkeypatch) -> None:
    from plugins.susi_ops import recommendation

    monkeypatch.setattr(recommendation, "_SCHOOL_TIER", {})
    wise_row = {
        "university_id": "149",
        "university": "동국대학교",
        "department": "스포츠과학전공",
        "score_logic_json": '{"formula_key":"DGU_WISE_2027_PRACTICAL"}',
        "raw_json": "{}",
    }
    seoul_row = {
        "university_id": "155",
        "university": "동국대학교",
        "department": "체육교육과",
        "score_logic_json": '{"formula_key":"DGU_2027_PRACTICAL"}',
        "raw_json": "{}",
    }
    glocal_row = {
        "university_id": "10",
        "university": "건국대학교",
        "department": "스포츠건강학과",
        "score_logic_json": "{}",
        "raw_json": '{"source_pdf_rel_path":"건국대학교(글로컬)"}',
    }

    assert recommendation._display_university_name(wise_row) == "동국대학교 WISE"
    assert recommendation._school_tier("동국대학교 WISE", "스포츠과학전공", "경북") == "C"
    assert recommendation._display_university_name(seoul_row) == "동국대학교"
    assert recommendation._school_tier("동국대학교", "체육교육과", "서울") == "S"
    assert recommendation._display_university_name(glocal_row) == "건국대학교(글로컬)"


def test_recommend_handler_same_turn_region_recall_allowed(monkeypatch) -> None:
    """현관 게이트 도입 후: 지역을 받은 턴의 재호출은 정상 통과해야 한다."""
    from plugins import susi_ops

    monkeypatch.setattr(
        susi_ops,
        "recommend_candidates",
        lambda **kw: {"need_region": True} if not kw.get("region") else {"total_feasible": 1, "candidates": []},
    )

    first = susi_ops._recommend_handler({"student_query": "서연"})
    assert first.get("need_region") is True
    second = susi_ops._recommend_handler({"student_query": "서연", "region": "서울, 경기, 인천, 강원, 충청"})
    assert second.get("total_feasible") == 1
