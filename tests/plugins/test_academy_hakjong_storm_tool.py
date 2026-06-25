from __future__ import annotations

from plugins.academy_ops.hakjong_storm_tool import (
    build_hakjong_storm_plan,
    register_hakjong_storm_tool,
)


class _FakeCtx:
    def __init__(self) -> None:
        self.tools: dict[str, dict] = {}

    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs


def test_hakjong_storm_plan_is_blocked_without_grounding() -> None:
    plan = build_hakjong_storm_plan(
        student_name="홍길동",
        university="국민대학교",
        department="스포츠건강재활학과",
        admission_track="국민프런티어",
        student_stage="grade3",
    )

    assert plan["ok"] is True
    assert plan["experimental"] is True
    assert plan["mode"] == "hakjong_storm_v0_safe_prewrite"
    assert plan["safety"]["status"] == "blocked"
    assert any("생기부" in flag for flag in plan["safety"]["flags"])
    assert any("정성 프로필" in flag for flag in plan["safety"]["flags"])
    assert plan["next_tool_chain"][0] == "life_record_lookup"


def test_hakjong_storm_plan_builds_perspective_questions_with_grounding() -> None:
    plan = build_hakjong_storm_plan(
        student_name="홍길동",
        university="경희대학교",
        department="체육학과",
        admission_track="네오르네상스",
        student_stage="grade3",
        qualitative_profile={
            "summary": "서류평가는 학업역량, 진로역량, 공동체역량을 종합 검토한다.",
            "evaluation_elements": ["학업역량", "진로역량", "공동체역량"],
            "interview_points": ["활동 동기", "전공 연결"],
        },
        student_record_facts=[
            "2학년 운동과 건강 세특에서 체력 측정 결과를 비교 분석함.",
            "진로활동에서 스포츠 재활 관련 탐구 주제를 정리함.",
        ],
        max_questions=12,
    )

    assert plan["safety"]["status"] == "ready_for_grounded_draft"
    assert len(plan["perspectives"]) == 6
    all_questions = [q for p in plan["perspectives"] for q in p["questions"]]
    assert len(all_questions) == 12
    assert any("경희대학교" in q and "체육학과" in q for q in all_questions)
    assert plan["source_digest"]["student_record_fact_count"] == 2
    assert plan["report_outline"][0]["section"].startswith("1.")


def test_hakjong_storm_accepts_full_qualitative_profile_result() -> None:
    plan = build_hakjong_storm_plan(
        student_name="홍길동",
        university="국민대학교",
        department="스포츠건강재활학과",
        admission_track="국민프런티어",
        student_stage="grade3",
        qualitative_profile={
            "ok": True,
            "profiles": [
                {
                    "summary": "스포츠건강재활학과는 전공적합성과 탐구 지속성을 본다.",
                    "evaluation_elements": ["진로역량", "학업역량"],
                    "subject_specific_notes": {"체육": "운동재활 탐구"},
                }
            ],
        },
        student_record_facts=["운동과 건강 세특에서 회복 운동을 조사함."],
    )

    assert plan["safety"]["status"] == "ready_for_grounded_draft"
    assert "profiles[0]" in plan["source_digest"]["qualitative_profile"]["fields_used"]


def test_hakjong_storm_grade1_prioritizes_record_design() -> None:
    plan = build_hakjong_storm_plan(
        student_name="홍길동",
        university="한양대학교",
        department="스포츠사이언스전공",
        student_stage="grade1",
        consultation_note="농구를 좋아하고 발목 부상 경험이 있어 부상예방과 회복에 관심이 있음.",
        qualitative_profile={"summary": "학과는 건강관리와 스포츠 데이터 해석을 강조한다."},
        max_questions=6,
    )

    assert plan["safety"]["status"] == "ready_for_grounded_draft"
    assert plan["perspectives"][0]["id"] == "major_and_career_fit"
    assert "기록 설계" in plan["report_outline"][1]["section"]
    assert "life_record_lookup 또는 상담메모" in plan["next_tool_chain"][0]


def test_hakjong_storm_handler_tolerates_bad_question_limit() -> None:
    ctx = _FakeCtx()
    register_hakjong_storm_tool(ctx)

    result = ctx.tools["hakjong_storm_prewrite"]["handler"](
        {
            "student_stage": "grade3",
            "max_questions": "숫자아님",
            "include_risk_checks": "false",
        }
    )

    assert result["ok"] is True
    assert len([q for p in result["perspectives"] for q in p["questions"]]) == 15
    assert all(p["id"] != "risk_and_bias_check" for p in result["perspectives"])


def test_hakjong_storm_tool_registration() -> None:
    ctx = _FakeCtx()
    register_hakjong_storm_tool(ctx)

    assert "hakjong_storm_prewrite" in ctx.tools
    tool = ctx.tools["hakjong_storm_prewrite"]
    assert tool["toolset"] == "academy_ops"
    assert tool["schema"]["additionalProperties"] is False
    assert "최종 PDF" in tool["description"]
