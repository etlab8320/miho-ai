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

from typing import Any

from .hakjong_report_contract import (
    BANNED_HAKJONG_ONLY_TEXT,
    BANNED_PDF_TEXT,
    MIN_VISIBLE_TEXT_CHARS,
    MAX_VISIBLE_TEXT_SEGMENT_CHARS,
)
from .hakjong_stage_contract import validate_stage_contract


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
    errors: list[str] = []
    checks: dict[str, Any] = {}
    tools = evidence_tools or []

    _validate_structure(content, errors)
    if errors:
        # Structure errors block quality checks — shape must be valid first.
        return False, errors

    _validate_quality(content, student_stage=student_stage, evidence_tools=tools, errors=errors, checks=checks)
    return not errors, errors


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
        gauges = diag.get("gauges")
        if not isinstance(gauges, list) or len(gauges) != 3:
            errors.append("content.diagnosis_section.gauges는 정확히 3개여야 한다.")

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
        if not isinstance(strat.get("interview_rows"), list) or not strat["interview_rows"]:
            errors.append("content.strategy_section.interview_rows는 1개 이상이어야 한다.")
        fj = strat.get("final_judgment")
        if not isinstance(fj, dict) or not _nonempty_str(fj.get("body")):
            errors.append("content.strategy_section.final_judgment.body가 비어 있다.")
        cl = strat.get("checklist")
        if not isinstance(cl, dict) or not _nonempty_str(cl.get("title")):
            errors.append("content.strategy_section.checklist.title이 비어 있다.")


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
    if not any(_matches_hakjong_evidence(t) for t in normalized):
        errors.append(
            "학종/입시 프로파일 근거가 없다. "
            "qualitative_profile / hakjong_profile / susi_engine 등을 먼저 호출해야 한다."
        )


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


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
