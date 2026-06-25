"""Content JSON validation for the hakjong report shell template.

T2: Validates the structure and quality of content JSON before Jinja2
rendering. All errors are returned in Korean so the agent can perform
one corrective pass.

Template structure (hakjong_report_shell.html):
  student: {name}
  university: {name, department, college, track}
  badge: {grade, action}
  title_lines: [".."]
  cover: {pills[], key_judgment{headline, body}, metrics[{label,value}]x3}
  track_section: {heading, info_cards[{label,value,sub}]x3,
                  rows[{label,official,judgment}],
                  strong_points{title,bullets[]}, caution_points{title,bullets[]},
                  footnote}
  diagnosis_section: {heading,
                  strength{headline,body}, risk{headline,body},
                  rows[{area,record,interpretation,check}],
                  gauges[{label,level,note,tone,percent}]x3,
                  footnote}
  strategy_section: {heading, actions[{title,body}]x4,
                  interview_rows[{question,point}],
                  final_judgment{body},
                  checklist{title,bullets[],tags[]},
                  footnote}
"""

from __future__ import annotations

import re
from typing import Any

from .hakjong_report_contract import (
    BANNED_HAKJONG_ONLY_TEXT,
    BANNED_PDF_TEXT,
    MIN_VISIBLE_TEXT_CHARS,
    MAX_VISIBLE_TEXT_SEGMENT_CHARS,
)
from .hakjong_stage_contract import validate_stage_contract

_STORM_EVIDENCE_TOOL = "hakjong_storm_prewrite"
_ENROLLED_STAGES = {"grade1", "grade2", "grade3"}
_PROJECT_METHOD_WORDS = (
    "측정",
    "분석",
    "비교",
    "데이터",
    "그래프",
    "조사",
    "기록",
    "실험",
    "관찰",
    "보고서",
    "발표",
    "프로토콜",
    "인터뷰",
    "설문",
    "통계",
)
_RECORD_LINK_WORDS = ("세특", "생기부", "기록", "활동", "탐구", "창체", "동아리", "진로")
_RESEARCH_LINK_WORDS = ("최신", "논문", "뉴스", "교수", "연구", "학과", "전공", "교육과정")
_INTERVIEW_NEGATIONS = ("면접 없음", "면접없음", "면접 미실시", "면접미실시", "면접 미반영", "서류 100", "서류100")
_STRATEGY_ADMISSION_FACT_WORDS = ("수능최저", "수능 최저", "최저학력")


def validate_content(
    content: dict[str, Any],
    *,
    student_stage: str = "",
    evidence_tools: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Validate content JSON structure and quality.

    Returns ``(ok, errors)`` where errors are Korean strings that describe
    exactly what the agent needs to fix.
    """
    ok, errors, _checks = validate_content_with_checks(
        content,
        student_stage=student_stage,
        evidence_tools=evidence_tools,
    )
    return ok, errors


def validate_content_with_checks(
    content: dict[str, Any],
    *,
    student_stage: str = "",
    evidence_tools: list[str] | None = None,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Validate content and return the quality facts written to the manifest."""
    errors: list[str] = []
    checks: dict[str, Any] = {}
    tools = evidence_tools or []

    _validate_structure(content, errors)
    if errors:
        return False, errors, checks

    _validate_quality(content, student_stage=student_stage, evidence_tools=tools, errors=errors, checks=checks)
    return not errors, errors, checks


# ---------------------------------------------------------------------------
# Structure validation
# ---------------------------------------------------------------------------

def _validate_structure(content: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(content, dict):
        errors.append("content는 dict여야 한다.")
        return

    # student
    student = content.get("student")
    if not isinstance(student, dict):
        errors.append("content.student 필드가 없거나 dict가 아니다.")
    else:
        if not _nonempty_str(student.get("name")):
            errors.append("content.student.name이 비어 있다.")

    # university
    university = content.get("university")
    if not isinstance(university, dict):
        errors.append("content.university 필드가 없거나 dict가 아니다.")
    else:
        for key in ("name", "department", "track"):
            if not _nonempty_str(university.get(key)):
                errors.append(f"content.university.{key}가 비어 있다.")

    # badge
    badge = content.get("badge")
    if not isinstance(badge, dict):
        errors.append("content.badge 필드가 없거나 dict가 아니다.")
    else:
        for key in ("grade", "action"):
            if not _nonempty_str(badge.get(key)):
                errors.append(f"content.badge.{key}가 비어 있다.")

    # title_lines
    title_lines = content.get("title_lines")
    if not isinstance(title_lines, list) or not title_lines:
        errors.append("content.title_lines는 1개 이상의 문자열 목록이어야 한다.")

    # cover
    cover = content.get("cover")
    if not isinstance(cover, dict):
        errors.append("content.cover 필드가 없거나 dict가 아니다.")
    else:
        if not isinstance(cover.get("pills"), list):
            errors.append("content.cover.pills는 list여야 한다.")
        kj = cover.get("key_judgment")
        if not isinstance(kj, dict) or not _nonempty_str(kj.get("headline")) or not _nonempty_str(kj.get("body")):
            errors.append("content.cover.key_judgment에 headline과 body가 필요하다.")
        metrics = cover.get("metrics")
        if not isinstance(metrics, list) or len(metrics) != 3:
            errors.append("content.cover.metrics는 정확히 3개의 항목(label/value)이어야 한다.")

    # track_section
    track = content.get("track_section")
    if not isinstance(track, dict):
        errors.append("content.track_section 필드가 없거나 dict가 아니다.")
    else:
        if not _nonempty_str(track.get("heading")):
            errors.append("content.track_section.heading이 비어 있다.")
        info_cards = track.get("info_cards")
        if not isinstance(info_cards, list) or len(info_cards) != 3:
            errors.append("content.track_section.info_cards는 정확히 3개여야 한다.")
        if not isinstance(track.get("rows"), list) or not track["rows"]:
            errors.append("content.track_section.rows는 1개 이상이어야 한다.")
        else:
            _validate_row_fields(track["rows"], "track_section.rows", ("label", "official", "judgment"), errors)
        _validate_pointbox(track.get("strong_points"), "track_section.strong_points", errors)
        _validate_pointbox(track.get("caution_points"), "track_section.caution_points", errors)

    # diagnosis_section
    diag = content.get("diagnosis_section")
    if not isinstance(diag, dict):
        errors.append("content.diagnosis_section 필드가 없거나 dict가 아니다.")
    else:
        if not _nonempty_str(diag.get("heading")):
            errors.append("content.diagnosis_section.heading이 비어 있다.")
        for sub in ("strength", "risk"):
            box = diag.get(sub)
            if not isinstance(box, dict) or not _nonempty_str(box.get("headline")) or not _nonempty_str(box.get("body")):
                errors.append(f"content.diagnosis_section.{sub}에 headline과 body가 필요하다.")
        if not isinstance(diag.get("rows"), list) or not diag["rows"]:
            errors.append("content.diagnosis_section.rows는 1개 이상이어야 한다.")
        else:
            _validate_row_fields(diag["rows"], "diagnosis_section.rows", ("area", "record", "interpretation", "check"), errors)
        gauges = diag.get("gauges")
        if not isinstance(gauges, list) or len(gauges) != 3:
            errors.append("content.diagnosis_section.gauges는 정확히 3개여야 한다.")
        else:
            _validate_row_fields(gauges, "diagnosis_section.gauges", ("label", "level", "note"), errors)

    # strategy_section
    strat = content.get("strategy_section")
    if not isinstance(strat, dict):
        errors.append("content.strategy_section 필드가 없거나 dict가 아니다.")
    else:
        if not _nonempty_str(strat.get("heading")):
            errors.append("content.strategy_section.heading이 비어 있다.")
        actions = strat.get("actions")
        if not isinstance(actions, list) or len(actions) != 4:
            errors.append("content.strategy_section.actions는 정확히 4개여야 한다.")
        if not isinstance(strat.get("interview_rows"), list):
            errors.append("content.strategy_section.interview_rows는 list여야 한다.")
        else:
            _validate_row_fields(strat["interview_rows"], "strategy_section.interview_rows", ("question", "point"), errors)
        fj = strat.get("final_judgment")
        if not isinstance(fj, dict) or not _nonempty_str(fj.get("body")):
            errors.append("content.strategy_section.final_judgment.body가 비어 있다.")
        # 세특 공백 학생은 gap_plan(세특 설계)이 체크리스트 자리를 대신한다.
        gap = strat.get("gap_plan")
        if not isinstance(gap, dict):
            cl = strat.get("checklist")
            if not isinstance(cl, dict) or not _nonempty_str(cl.get("title")):
                errors.append("content.strategy_section.checklist.title이 비어 있다.")


def _validate_row_fields(rows: Any, path: str, fields: tuple[str, ...], errors: list[str]) -> None:
    """표의 모든 행은 모든 칸이 채워져야 한다 — 라벨만 있고 내용이 빈 표가
    스키마를 통과해 학생용 PDF에 그대로 인쇄된 실사고(2026-06-12 유가은 리포트) 방지."""
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"content.{path}[{i}]가 dict가 아니다.")
            continue
        for f in fields:
            if not _nonempty_str(str(row.get(f) or "")):
                errors.append(f"content.{path}[{i}].{f}가 비어 있다 — 표의 모든 칸을 채워라.")


def _validate_pointbox(box: Any, path: str, errors: list[str]) -> None:
    if not isinstance(box, dict) or not _nonempty_str(box.get("title")):
        errors.append(f"content.{path}.title이 비어 있다.")
    elif not isinstance(box.get("bullets"), list) or not box["bullets"]:
        errors.append(f"content.{path}.bullets는 1개 이상이어야 한다.")


# ---------------------------------------------------------------------------
# Quality validation (ported from hakjong_report_contract)
# ---------------------------------------------------------------------------

def _validate_quality(
    content: dict[str, Any],
    *,
    student_stage: str,
    evidence_tools: list[str],
    errors: list[str],
    checks: dict[str, Any],
) -> None:
    strings = _collect_strings(content)

    # Total visible text
    total_chars = sum(len(s) for s in strings)
    checks["visible_text_chars"] = total_chars
    if total_chars < MIN_VISIBLE_TEXT_CHARS:
        errors.append(
            f"전체 텍스트가 {total_chars}자로 너무 짧다 (최소 {MIN_VISIBLE_TEXT_CHARS}자 필요). "
            "각 섹션의 본문을 더 구체적으로 작성하라."
        )

    # Overlong single text blocks
    overlong = [s for s in strings if len(s) > MAX_VISIBLE_TEXT_SEGMENT_CHARS]
    checks["overlong_segments"] = len(overlong)
    if overlong:
        sample = overlong[0][:40] + "…"
        errors.append(
            f"단일 텍스트 블록이 {MAX_VISIBLE_TEXT_SEGMENT_CHARS}자를 초과했다 "
            f"({len(overlong)}개, 예: \"{sample}\"). "
            "문단·카드 body를 짧게 나눠라."
        )

    # Banned wording
    all_text = " ".join(strings)
    for banned in BANNED_PDF_TEXT:
        if banned in all_text:
            errors.append(f"금지 문구가 포함됐다: \"{banned}\". 삭제하거나 다른 표현으로 바꿔라.")
    for banned in BANNED_HAKJONG_ONLY_TEXT:
        if banned in all_text:
            errors.append(
                f"학종 리포트에 \"{banned}\" 언급 금지 — 학종은 생기부(교과·세특·활동)와 서류·면접 이야기만 한다. "
                "실기 측정 기록이나 다른 전형과의 비교 설명은 전부 빼고 다시 호출하라."
            )

    _validate_strategy_actions(content, errors)

    # Stage contract: reuse hakjong_stage_contract with text as visible_text list
    validate_stage_contract(
        student_stage=student_stage,
        visible_text=strings,
        evidence_tools=evidence_tools,
        errors=errors,
        checks=checks,
    )

    # Evidence tools
    _validate_evidence(evidence_tools, student_stage=checks.get("student_stage", ""), errors=errors, checks=checks)
    _validate_storm_contract(content, student_stage=checks.get("student_stage", ""), errors=errors, checks=checks)


def _validate_evidence(
    evidence_tools: list[str],
    *,
    student_stage: str,
    errors: list[str],
    checks: dict[str, Any],
) -> None:
    """Ported from hakjong_report_contract._validate_evidence."""
    from .hakjong_report_contract import (
        LIFE_RECORD_EVIDENCE_TOOLS,
        _matches_hakjong_evidence,
    )
    from .hakjong_stage_contract import has_early_context_evidence

    normalized = {str(t).strip() for t in evidence_tools if str(t).strip()}
    checks["evidence_tools"] = sorted(normalized)
    needs_life_record = student_stage in {"grade3", "graduate"} or not student_stage
    if needs_life_record and not (normalized & LIFE_RECORD_EVIDENCE_TOOLS):
        errors.append(
            "생기부 근거 도구가 없다. 리포트를 작성하기 전에 "
            "life_record_lookup / life_record_summary / life_record_search를 먼저 호출해야 한다."
        )
    elif not needs_life_record and not (
        bool(normalized & LIFE_RECORD_EVIDENCE_TOOLS) or has_early_context_evidence(normalized)
    ):
        errors.append(
            "학생 컨텍스트 근거가 없다. 상담/생기부 근거 도구를 먼저 호출해야 한다."
        )
    hakjong_sources = normalized - {_STORM_EVIDENCE_TOOL}
    if not any(_matches_hakjong_evidence(t) for t in hakjong_sources):
        errors.append(
            "학종/입시 프로파일 근거가 없다. "
            "qualitative_profile / hakjong_profile / susi_engine 등을 먼저 호출해야 한다."
        )
    if _STORM_EVIDENCE_TOOL not in normalized:
        errors.append(
            "STORM 사전설계 근거가 없다. 학종 PDF는 life_record_*와 hakjong_qualitative_profile 확인 후 "
            "hakjong_storm_prewrite로 관점별 질문·근거 슬롯·과잉해석 리스크를 먼저 잠가야 한다."
        )


def _validate_storm_contract(
    content: dict[str, Any],
    *,
    student_stage: str,
    errors: list[str],
    checks: dict[str, Any],
) -> None:
    strategy = content.get("strategy_section") if isinstance(content, dict) else {}
    strategy = strategy if isinstance(strategy, dict) else {}

    interview_required = _interview_required(content)
    checks["interview_required"] = interview_required
    interview_rows = strategy.get("interview_rows")
    interview_rows = interview_rows if isinstance(interview_rows, list) else []
    checks["interview_question_count"] = len(interview_rows)
    if interview_required:
        _validate_interview_rows(interview_rows, errors)

    if student_stage not in _ENROLLED_STAGES:
        return

    gap = strategy.get("gap_plan")
    subjects = gap.get("subjects") if isinstance(gap, dict) else None
    subjects = subjects if isinstance(subjects, list) else []
    checks["gap_project_count"] = len(subjects)
    if len(subjects) < 3:
        errors.append(
            "재학생 학종 리포트는 strategy_section.gap_plan.subjects에 과세특·활동 프로젝트를 3개 이상 제시해야 한다. "
            "기존 생기부 연계 프로젝트와 학과/논문/뉴스 기반 신규 프로젝트를 섞어라."
        )
        return

    all_project_text = _content_text(subjects)
    if not any(word in all_project_text for word in _RECORD_LINK_WORDS):
        errors.append("gap_plan 전체에 학생 기존 생기부·세특·활동 기록과의 연결이 없다.")
    if not any(word in all_project_text for word in _RESEARCH_LINK_WORDS):
        errors.append("gap_plan 전체에 학과 교육과정·교수 연구·논문·최신 뉴스 흐름과의 연결이 없다.")

    for idx, subject in enumerate(subjects):
        if not isinstance(subject, dict):
            errors.append(f"strategy_section.gap_plan.subjects[{idx}]가 dict가 아니다.")
            continue
        missing = [
            key
            for key in ("field", "current_record", "school_direction", "eval_axis", "expected_effect")
            if not _nonempty_str(subject.get(key))
        ]
        if missing:
            errors.append(f"strategy_section.gap_plan.subjects[{idx}]에 필수 필드가 비어 있다: {', '.join(missing)}.")
        steps = subject.get("steps")
        if not isinstance(steps, list) or len(steps) < 3:
            errors.append(f"strategy_section.gap_plan.subjects[{idx}].steps는 3개 이상이어야 한다.")
            continue
        step_text = " ".join(str(step) for step in steps)
        method_hits = sum(1 for word in _PROJECT_METHOD_WORDS if word in step_text)
        if method_hits < 2:
            errors.append(
                f"strategy_section.gap_plan.subjects[{idx}]는 측정·분석·비교·데이터화 같은 구체 방법이 부족하다."
            )


def _validate_strategy_actions(content: dict[str, Any], errors: list[str]) -> None:
    strategy = content.get("strategy_section") if isinstance(content, dict) else {}
    actions = strategy.get("actions") if isinstance(strategy, dict) else []
    if not isinstance(actions, list):
        return
    for idx, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        text = _content_text(action)
        if any(word in text for word in _STRATEGY_ADMISSION_FACT_WORDS):
            errors.append(
                f"보완 전략 actions[{idx}]에 수능최저 같은 전형 조건을 섞지 마라. "
                "수능최저는 전형 구조에만 쓰고, 세특 보완 전략은 교과·활동·탐구 방법으로 작성하라."
            )
        if re.compile(r"면접[^.。]*\d+\s*%").search(text):
            errors.append(
                f"보완 전략 actions[{idx}]에 면접 반영비율을 섞지 마라. "
                "면접 비율은 전형 구조에만 쓰고, 면접 준비는 질문·근거·꼬리질문 방어로 작성하라."
            )


def _validate_interview_rows(rows: list[Any], errors: list[str]) -> None:
    if len(rows) < 5:
        errors.append("면접 반영 전형은 strategy_section.interview_rows를 5개 이상 넣어야 한다.")
        return
    text = _content_text(rows)
    if not any(word in text for word in ("꼬리질문", "추가 질문", "재질문", "면접관")):
        errors.append("면접 반영 전형은 답변 포인트에 꼬리질문/재질문 방어 포인트가 드러나야 한다.")
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if len(str(row.get("question") or "").strip()) < 12:
            errors.append(f"strategy_section.interview_rows[{idx}].question이 너무 짧다.")
        if len(str(row.get("point") or "").strip()) < 50:
            errors.append(f"strategy_section.interview_rows[{idx}].point는 답변 근거·방어 포인트까지 50자 이상 써야 한다.")


def _interview_required(content: dict[str, Any]) -> bool:
    track = content.get("track_section") if isinstance(content, dict) else {}
    official_parts: list[Any] = []
    if isinstance(track, dict):
        official_parts.append(track.get("info_cards"))
        for row in track.get("rows") or []:
            if isinstance(row, dict):
                official_parts.extend([row.get("label"), row.get("official")])
    chunks = _collect_strings(official_parts)
    interview_chunks = [chunk for chunk in chunks if "면접" in chunk]
    if not interview_chunks:
        return False
    if any(re.compile(r"면접[^,.;]*(\d|%)").search(chunk) for chunk in interview_chunks):
        return True
    return not any(negation in chunk for chunk in interview_chunks for negation in _INTERVIEW_NEGATIONS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_strings(obj: Any) -> list[str]:
    """Recursively collect all non-empty string leaf values."""
    result: list[str] = []
    if isinstance(obj, str):
        stripped = obj.strip()
        if stripped:
            result.append(stripped)
    elif isinstance(obj, dict):
        for value in obj.values():
            result.extend(_collect_strings(value))
    elif isinstance(obj, list):
        for item in obj:
            result.extend(_collect_strings(item))
    return result


def _content_text(obj: Any) -> str:
    return " ".join(_collect_strings(obj))


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
