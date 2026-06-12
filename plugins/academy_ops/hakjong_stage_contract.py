"""Stage-specific contract for hakjong student reports."""

from __future__ import annotations

from typing import Any


EARLY_CONTEXT_EVIDENCE = {
    "consultation_note",
    "consultation_notes",
    "student_interview",
    "student_context",
    "counseling_text",
    "academy_consultation_note_save",
}

STAGE_ALIASES = {
    "grade1": {"1", "1학년", "고1", "grade1", "first_year"},
    "grade2": {"2", "2학년", "고2", "grade2", "second_year"},
    "grade3": {"3", "3학년", "고3", "grade3", "third_year"},
    "graduate": {"n", "n수", "n수생", "재수", "재수생", "졸업생", "graduate", "repeat", "n_susaeng"},
}

STAGE_REQUIRED_GROUPS = {
    "grade1": (
        ("상담 기반", ("상담", "관심", "학교생활", "장점", "강점", "목표")),
        ("생활기록부 시작 설계", ("생활기록부 시작", "기록 설계", "탐구 축", "활동 설계")),
        ("학교/학과 연결", ("대학", "학과", "인재상", "평가 요소")),
    ),
    "grade2": (
        ("1학년 기록 연결", ("1학년", "기존 기록", "이어갈", "끊긴 흐름")),
        ("2학년 기록 설계", ("2학년", "선택과목", "동아리", "진로활동", "탐구 축")),
        ("학교/학과 연결", ("대학", "학과", "인재상", "평가 요소")),
    ),
    "grade3": (
        # 확정 디자인(안시현 리포트) 어휘 반영: 최종 판단은 상향/적정/안정권 등급 언어로 표현된다.
        ("지원 가능성 판단", ("지원 가능", "지원 판단", "추천", "비추천", "전략 부적합", "상향", "적정", "안정권", "보완 후 검토")),
        ("보완 전략", ("보완", "준비", "전략", "면접", "세특", "진로활동")),
        ("학교/학과 연결", ("대학", "학과", "인재상", "평가 요소", "전형")),
    ),
    "graduate": (
        ("완성 생기부 분석", ("완성", "학생부", "생기부", "기록 근거")),
        ("지원 가능성 판단", ("지원 가능", "지원 판단", "추천", "비추천", "전략 부적합", "상향", "적정", "안정권", "보완 후 검토")),
        ("면접 방어", ("면접", "방어", "설명력", "질문")),
    ),
}

STAGE_BANNED_TERMS = {
    "grade1": ("완성된 학생부", "생기부 분석 결과", "면접 방어 전략 중심"),
    "grade2": ("완성된 학생부", "면접 방어 전략 중심"),
    "grade3": ("처음부터 스토리 만들기", "생활기록부 시작 설계"),
    "graduate": ("세특 입력 전", "과세특 디벨롭", "생활기록부 시작 설계"),
}


def normalize_student_stage(value: str) -> str:
    clean = str(value or "").strip().lower().replace(" ", "")
    for stage, aliases in STAGE_ALIASES.items():
        if clean in {alias.lower().replace(" ", "") for alias in aliases}:
            return stage
    return ""


def validate_stage_contract(
    *,
    student_stage: str,
    visible_text: list[str],
    evidence_tools: list[str],
    errors: list[str],
    checks: dict[str, Any],
) -> str:
    stage = normalize_student_stage(student_stage)
    checks["student_stage"] = stage or str(student_stage or "").strip()
    if not stage:
        errors.append("student_stage is required: grade1, grade2, grade3, or graduate")
        return ""

    body = " ".join(visible_text)
    missing_groups = [
        label
        for label, terms in STAGE_REQUIRED_GROUPS[stage]
        if not any(term in body for term in terms)
    ]
    checks["stage_required_groups_missing"] = missing_groups
    if missing_groups:
        errors.append(
            f"{stage} report is missing stage-specific sections: " + ", ".join(missing_groups)
        )

    banned_terms = [term for term in STAGE_BANNED_TERMS[stage] if term in body]
    checks["stage_banned_terms"] = banned_terms
    if banned_terms:
        errors.append(f"{stage} report contains wrong-stage wording: " + ", ".join(banned_terms))

    normalized_evidence = {str(tool).strip() for tool in evidence_tools if str(tool).strip()}
    if stage in {"grade1", "grade2"} and not has_early_context_evidence(normalized_evidence):
        errors.append("early-grade report requires counseling/student-context evidence")

    return stage


def has_early_context_evidence(evidence_tools: set[str]) -> bool:
    return bool(evidence_tools & EARLY_CONTEXT_EVIDENCE)
