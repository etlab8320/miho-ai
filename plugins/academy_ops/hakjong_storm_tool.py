"""Experimental STORM-style planner for hakjong qualitative review.

This module does **not** generate final admission judgments. It creates a safe
pre-writing/research scaffold: perspectives -> questions -> evidence slots ->
outline. The final PDF/report flow must still use the existing grounded tools
(`hakjong_qualitative_profile`, `life_record_*`, `susi27_rule_lookup`, and
`academy_hakjong_report_package`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any


_MAX_TEXT = 900
_DEFAULT_MAX_QUESTIONS = 18

_PERSPECTIVE_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "id": "admission_rubric_fit",
        "name": "대학 평가요소 적합도",
        "focus": "대학·전형이 실제로 보는 평가축과 학생 기록의 맞물림을 확인한다.",
        "question_templates": (
            "{university} {department} {track}의 공식 평가요소 중 학생 기록으로 가장 강하게 입증되는 축은 무엇인가?",
            "평가요소 대비 근거가 약하거나 비어 있는 축은 무엇이며, 학생/학부모에게 어떻게 설명해야 하는가?",
            "전형방법·면접비중·수능최저 등 구조상 이 학생에게 불리하게 작용할 지점은 무엇인가?",
        ),
        "evidence_queries": ("전형방법", "서류평가 요소", "면접평가 요소", "수능최저", "모집요강"),
    },
    {
        "id": "academic_competency",
        "name": "학업역량",
        "focus": "교과 성취와 세특의 사고력·탐구력·문제해결력을 분리해 본다.",
        "question_templates": (
            "학생부에서 학업역량을 보여주는 과목·세특·탐구 문장은 어디인가?",
            "성적 약점이 있다면 세특/탐구 기록이 이를 어느 정도 보완하는가?",
            "목표 학과의 학문 기반과 연결되는 교과 기록은 무엇이며, 근거 강도는 어느 수준인가?",
        ),
        "evidence_queries": ("교과 성취", "세특", "탐구활동", "학업역량", "과목별 기록"),
    },
    {
        "id": "major_and_career_fit",
        "name": "전공·진로 적합성",
        "focus": "관심 표명이 아니라 활동-탐구-진로 확장 흐름이 있는지 본다.",
        "question_templates": (
            "{department}와 직접 연결되는 활동·세특·진로 기록은 무엇인가?",
            "단발 활동이 아니라 누적된 관심/탐구/실천 흐름으로 읽히는가?",
            "체육계열 기록을 학과 평가어로 바꾸면 어떤 키워드가 살아나는가?",
        ),
        "evidence_queries": ("전공적합성", "진로활동", "동아리", "창체", "학과 키워드"),
    },
    {
        "id": "narrative_coherence",
        "name": "학생부 서사 일관성",
        "focus": "세특·창체·진로·행특이 하나의 설득 가능한 성장 서사로 이어지는지 본다.",
        "question_templates": (
            "학생의 기록은 어떤 성장 서사로 묶을 수 있으며, 억지 연결은 없는가?",
            "세특-동아리-진로활동-행특 사이에 끊기는 구간은 어디인가?",
            "상담 리포트에서 강조할 핵심 장면 3개와 빼야 할 약한 장면은 무엇인가?",
        ),
        "evidence_queries": ("성장 과정", "활동 연계", "행특", "진로 변경", "핵심 사례"),
    },
    {
        "id": "interview_defense",
        "name": "면접 방어와 꼬리질문",
        "focus": "서류에서 면접관이 파고들 지점과 답변 소재를 미리 분리한다.",
        "question_templates": (
            "면접관이 학생부에서 가장 먼저 물어볼 질문 5개는 무엇인가?",
            "학생이 설명하지 못하면 위험한 활동·세특·진로 표현은 무엇인가?",
            "답변은 어떤 실제 경험 → 배운 점 → 학과 연결 순서로 잡아야 하는가?",
        ),
        "evidence_queries": ("면접 질문", "꼬리 질문", "답변 근거", "학생부 표현", "서류 방어"),
    },
    {
        "id": "risk_and_bias_check",
        "name": "리스크·과잉해석 점검",
        "focus": "출처 편향, 근거 없는 연결, 학부모용 표현 위험을 마지막에 걷어낸다.",
        "question_templates": (
            "학생부에 없는 내용을 AI가 추정하거나 미화한 부분은 없는가?",
            "A와 B는 사실이어도 둘 사이의 인과관계가 검증되지 않은 연결은 없는가?",
            "내부용 냉정 판단과 학생/학부모용 표현을 어떻게 분리해야 하는가?",
        ),
        "evidence_queries": ("근거 없음", "과잉 해석", "출처 편향", "리스크", "표현 필터"),
    },
)

_STAGE_LABELS = {
    "grade1": "고1",
    "grade2": "고2",
    "grade3": "고3",
    "graduate": "졸업생/N수생",
}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _clean_text(value: Any, *, limit: int = _MAX_TEXT) -> str:
    text = re.sub(r"\s+", " ", _as_text(value)).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_clean_text(value)] if value.strip() else []
    if isinstance(value, Iterable) and not isinstance(value, (dict, bytes, bytearray)):
        out: list[str] = []
        for item in value:
            text = _clean_text(item)
            if text:
                out.append(text)
        return out
    text = _clean_text(value)
    return [text] if text else []


def _profile_summary(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        text = _clean_text(profile)
        return {"provided": bool(text), "summary": text}

    profile, source_label = _first_profile(profile)
    keys = (
        "summary",
        "evaluation_elements",
        "desired_record_keywords",
        "subject_specific_notes",
        "interview_points",
        "recent_result_avg_grade",
        "recent_result_note",
        "live_research",
    )
    compact = {key: profile.get(key) for key in keys if profile.get(key) not in (None, "", [], {})}
    fields_used = sorted(compact.keys())
    if source_label and fields_used:
        fields_used.insert(0, source_label)
    return {
        "provided": bool(compact),
        "summary": _clean_text(compact, limit=1400),
        "fields_used": fields_used,
    }


def _first_profile(profile: dict[str, Any]) -> tuple[dict[str, Any], str]:
    profiles = profile.get("profiles")
    if isinstance(profiles, list) and profiles and isinstance(profiles[0], dict):
        return profiles[0], "profiles[0]"
    return profile, ""


def _int_between(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _bool_value(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"false", "0", "no", "n", "off", "아니오", "아님"}:
            return False
        if text in {"true", "1", "yes", "y", "on", "예", "맞음"}:
            return True
    return bool(value)


def _format_question(template: str, *, university: str, department: str, track: str) -> str:
    return template.format(
        university=university or "목표 대학",
        department=department or "목표 학과",
        track=track or "해당 전형",
    )


def _select_perspectives(student_stage: str, include_risk: bool) -> list[dict[str, Any]]:
    perspectives = list(_PERSPECTIVE_TEMPLATES)
    if not include_risk:
        perspectives = [p for p in perspectives if p["id"] != "risk_and_bias_check"]
    # 고1·고2는 합불 판단보다 기록 설계가 중심이므로 서사/전공/학업을 앞에 둔다.
    if student_stage in {"grade1", "grade2"}:
        order = ["major_and_career_fit", "academic_competency", "narrative_coherence", "admission_rubric_fit", "interview_defense", "risk_and_bias_check"]
        rank = {pid: i for i, pid in enumerate(order)}
        perspectives.sort(key=lambda p: rank.get(p["id"], 99))
    return perspectives


def _build_outline(student_stage: str) -> list[dict[str, str]]:
    if student_stage in {"grade1", "grade2"}:
        return [
            {"section": "1. 현재 학생 맥락", "purpose": "상담 메모/초기 기록을 기준으로 희망학과·강점·공백을 정리"},
            {"section": "2. 평가 관점별 기록 설계", "purpose": "학업·전공·진로·공동체역량별로 앞으로 남길 기록을 설계"},
            {"section": "3. 과목/창체 액션", "purpose": "교과 세특과 자율·동아리·진로활동을 실제 실행 단위로 분리"},
            {"section": "4. 상담용 결론", "purpose": "학생/학부모에게 전달할 이번 학기 우선순위 정리"},
        ]
    return [
        {"section": "1. 전형 구조와 평가축", "purpose": "모집요강·정성 프로필 기반으로 대학이 보는 기준 확정"},
        {"section": "2. 학생부 근거 매칭", "purpose": "세특·창체·진로·행특을 평가축별로 연결하고 근거 강도 표시"},
        {"section": "3. 리스크와 방어", "purpose": "성적/출결/전공연계 공백, 과잉해석, 면접 취약점을 분리"},
        {"section": "4. 최종 전략", "purpose": "추천/보류/비추천 판단과 면접·보완 액션 정리"},
    ]


def build_hakjong_storm_plan(
    *,
    student_name: str = "",
    university: str = "",
    department: str = "",
    admission_track: str = "",
    student_stage: str = "",
    qualitative_profile: Any = None,
    student_record_facts: Any = None,
    consultation_note: str = "",
    max_questions: int = _DEFAULT_MAX_QUESTIONS,
    include_risk_checks: bool = True,
) -> dict[str, Any]:
    """Build a deterministic STORM-style pre-writing plan for hakjong review."""
    stage = str(student_stage or "").strip().lower()
    stage_label = _STAGE_LABELS.get(stage, "미지정")
    facts = _string_list(student_record_facts)
    note = _clean_text(consultation_note, limit=1200)
    profile = _profile_summary(qualitative_profile)
    max_q = _int_between(max_questions, default=_DEFAULT_MAX_QUESTIONS, minimum=6, maximum=30)

    perspectives = []
    question_budget = max_q
    selected = _select_perspectives(stage, include_risk_checks)
    per_perspective = max(1, question_budget // max(1, len(selected)))
    remainder = question_budget % max(1, len(selected))

    for idx, template in enumerate(selected):
        take = per_perspective + (1 if idx < remainder else 0)
        questions = [
            _format_question(q, university=university, department=department, track=admission_track)
            for q in template["question_templates"][:take]
        ]
        perspectives.append(
            {
                "id": template["id"],
                "name": template["name"],
                "focus": template["focus"],
                "questions": questions,
                "evidence_queries": list(template["evidence_queries"]),
                "evidence_strength_scale": ["강함", "보통", "약함", "없음"],
                "output_slot": "판단 / 근거 / 근거강도 / 리스크 / 보완액션",
            }
        )

    safety_flags: list[str] = []
    if not profile.get("provided"):
        safety_flags.append("학종 정성 프로필이 없으므로 대학별 평가축은 추정 금지")
    if not facts and not note:
        safety_flags.append("생기부/상담 근거가 없으므로 학생 판단 생성 금지")
    if stage in {"grade3", "graduate"} and not facts:
        safety_flags.append("고3·졸업생은 life_record 근거 없이 PDF/최종 판단 금지")
    if not university or not department:
        safety_flags.append("목표 대학/학과가 비어 있으면 대학별 적합도 판단 금지")

    required_next_tools = ["hakjong_qualitative_profile", "susi27_rule_lookup"]
    if stage in {"grade3", "graduate", ""}:
        required_next_tools.insert(0, "life_record_lookup")
    else:
        required_next_tools.insert(0, "life_record_lookup 또는 상담메모/초기 컨텍스트")

    return {
        "ok": True,
        "experimental": True,
        "mode": "hakjong_storm_v0_safe_prewrite",
        "student": {
            "name": student_name,
            "stage": stage or "unspecified",
            "stage_label": stage_label,
        },
        "target": {
            "university": university,
            "department": department,
            "admission_track": admission_track,
        },
        "source_digest": {
            "qualitative_profile": profile,
            "student_record_fact_count": len(facts),
            "student_record_facts_sample": facts[:8],
            "consultation_note": note,
        },
        "perspectives": perspectives,
        "report_outline": _build_outline(stage),
        "safety": {
            "status": "blocked" if safety_flags else "ready_for_grounded_draft",
            "flags": safety_flags,
            "rules": [
                "이 출력은 최종 판단이 아니라 사전조사/질문 설계다.",
                "각 판단은 학생부 또는 상담 근거 문장과 연결될 때만 리포트에 반영한다.",
                "출처에 있는 사실끼리도 인과관계는 별도 검증 전까지 연결하지 않는다.",
                "학생/학부모용 문장은 내부 냉정 판단을 순화하되 근거 강도는 숨기지 않는다.",
            ],
        },
        "next_tool_chain": required_next_tools + ["academy_hakjong_report_package"],
    }


def _handler(args: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
    payload = args or {}
    return build_hakjong_storm_plan(
        student_name=str(payload.get("student_name") or ""),
        university=str(payload.get("university") or ""),
        department=str(payload.get("department") or ""),
        admission_track=str(payload.get("admission_track") or ""),
        student_stage=str(payload.get("student_stage") or ""),
        qualitative_profile=payload.get("qualitative_profile"),
        student_record_facts=payload.get("student_record_facts"),
        consultation_note=str(payload.get("consultation_note") or ""),
        max_questions=_int_between(
            payload.get("max_questions"),
            default=_DEFAULT_MAX_QUESTIONS,
            minimum=6,
            maximum=30,
        ),
        include_risk_checks=_bool_value(payload.get("include_risk_checks", True)),
    )


def register_hakjong_storm_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="hakjong_storm_prewrite",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_name": {"type": "string", "description": "선택: 학생명."},
                "university": {"type": "string", "description": "목표 대학명."},
                "department": {"type": "string", "description": "목표 학과/모집단위."},
                "admission_track": {"type": "string", "description": "전형명."},
                "student_stage": {
                    "type": "string",
                    "enum": ["grade1", "grade2", "grade3", "graduate", ""],
                    "description": "학생 단계. 고3/졸업생은 생기부 근거 없이는 최종 판단 금지.",
                },
                "qualitative_profile": {
                    "type": "object",
                    "description": "hakjong_qualitative_profile 결과 중 해당 profile 1개. 없으면 대학별 평가축 추정 금지 플래그가 선다.",
                },
                "student_record_facts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "life_record_*에서 확인한 학생부 근거 문장 요약 목록.",
                },
                "consultation_note": {"type": "string", "description": "고1·고2 초기 상담 메모 또는 원장 상담 맥락."},
                "max_questions": {"type": "integer", "minimum": 6, "maximum": 30, "default": 18},
                "include_risk_checks": {"type": "boolean", "default": True},
            },
            "required": [],
            "additionalProperties": False,
        },
        handler=_handler,
        description=(
            "실험 기능: Stanford STORM 패턴을 학종 상담에 맞춘 안전한 사전조사 플래너. "
            "학생/전형을 관점별로 쪼개 질문·근거 슬롯·아웃라인을 만든다. "
            "최종 PDF를 만들기 전, hakjong_qualitative_profile·life_record_*·susi27_rule_lookup으로 확보한 "
            "근거를 어떻게 읽을지 설계할 때만 사용한다. 이 도구의 출력만으로 합격/불합격 판단이나 PDF를 만들지 말 것."
        ),
    )
