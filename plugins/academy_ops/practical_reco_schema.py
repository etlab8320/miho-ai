"""Content JSON validation for the practical_reco_shell.html template.

Validates structure and quality of content JSON before Jinja2 rendering.
All errors are returned in Korean so the agent can perform one corrective pass.

Template structure (practical_reco_shell.html):
  student: {name, avg_grade, basis_label}
  title_lines: [".."]
  badge: {line1, line2}
  cover: {pills[], key_judgment{headline, body}, metrics[{label,value}]x3}
  comparison: {note, rows[{school, department, track, converted, max_total,
                           first_cut, final_cut, verdict(상향|적정)}]}
  schools: [{name, department, track, verdict,
             numbers[{label,value}], events[], rationale_paragraphs[], caution}]
  final: {cards[{title,body}], callout{title, paragraphs[]}, tags[]}
  footnote
"""

from __future__ import annotations

from typing import Any

from .hakjong_report_contract import (
    BANNED_PDF_TEXT,
    MAX_VISIBLE_TEXT_SEGMENT_CHARS,
)

_MIN_VISIBLE_TEXT_CHARS = 800
_VALID_VERDICTS = {"상향", "적정"}
_MAX_ROWS = 8


def validate_content(
    content: dict[str, Any],
    *,
    evidence_tools: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Validate content JSON structure and quality.

    Returns ``(ok, errors)`` where errors are Korean strings describing
    exactly what the agent needs to fix.
    """
    errors: list[str] = []
    tools = evidence_tools or []

    _validate_structure(content, errors)
    if errors:
        return False, errors

    _validate_quality(content, evidence_tools=tools, errors=errors)
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
        if not _nonempty_str(student.get("basis_label")):
            errors.append("content.student.basis_label이 비어 있다.")

    # title_lines
    title_lines = content.get("title_lines")
    if not isinstance(title_lines, list) or not title_lines:
        errors.append("content.title_lines는 1개 이상의 문자열 목록이어야 한다.")

    # badge(도장)는 사장님 피드백(2026-06-12)으로 템플릿에서 제거됨 — 검증하지 않는다.

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

    # comparison
    comparison = content.get("comparison")
    if not isinstance(comparison, dict):
        errors.append("content.comparison 필드가 없거나 dict가 아니다.")
    else:
        rows = comparison.get("rows")
        if not isinstance(rows, list) or not rows:
            errors.append("content.comparison.rows는 1개 이상이어야 한다.")
        elif len(rows) > _MAX_ROWS:
            errors.append(f"content.comparison.rows는 최대 {_MAX_ROWS}개까지 허용된다 (현재 {len(rows)}개).")
        else:
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    errors.append(f"content.comparison.rows[{i}]는 dict여야 한다.")
                    continue
                for field in ("school", "department", "track", "converted", "max_total", "first_cut", "final_cut"):
                    if not _nonempty_str(row.get(field)):
                        errors.append(
                            f"content.comparison.rows[{i}].{field}가 비어 있다 "
                            "(환산점수 숫자는 반드시 채워야 한다)."
                        )
                verdict = row.get("verdict")
                if verdict not in _VALID_VERDICTS:
                    errors.append(
                        f"content.comparison.rows[{i}].verdict는 '상향' 또는 '적정'이어야 한다 "
                        f"(현재값: {verdict!r})."
                    )

    # schools — length must equal comparison.rows length
    schools = content.get("schools")
    if not isinstance(schools, list) or not schools:
        errors.append("content.schools는 1개 이상의 항목이어야 한다.")
    else:
        # Cross-check length with comparison rows (only when comparison is valid)
        if isinstance(comparison, dict) and isinstance(comparison.get("rows"), list):
            rows_len = len(comparison["rows"])
            if len(schools) != rows_len:
                errors.append(
                    f"content.schools 길이({len(schools)})가 "
                    f"content.comparison.rows 길이({rows_len})와 다르다."
                )
        for i, school in enumerate(schools):
            if not isinstance(school, dict):
                errors.append(f"content.schools[{i}]는 dict여야 한다.")
                continue
            for field in ("name", "department", "track"):
                if not _nonempty_str(school.get(field)):
                    errors.append(f"content.schools[{i}].{field}가 비어 있다.")
            verdict = school.get("verdict")
            if verdict not in _VALID_VERDICTS:
                errors.append(
                    f"content.schools[{i}].verdict는 '상향' 또는 '적정'이어야 한다 "
                    f"(현재값: {verdict!r})."
                )
            numbers = school.get("numbers")
            if not isinstance(numbers, list) or not numbers:
                errors.append(f"content.schools[{i}].numbers는 1개 이상이어야 한다.")
            if not isinstance(school.get("rationale_paragraphs"), list) or not school["rationale_paragraphs"]:
                errors.append(f"content.schools[{i}].rationale_paragraphs는 1개 이상이어야 한다.")

    # final
    final = content.get("final")
    if not isinstance(final, dict):
        errors.append("content.final 필드가 없거나 dict가 아니다.")
    else:
        cards = final.get("cards")
        if not isinstance(cards, list) or not cards:
            errors.append("content.final.cards는 1개 이상이어야 한다.")
        callout = final.get("callout")
        if not isinstance(callout, dict):
            errors.append("content.final.callout 필드가 없거나 dict가 아니다.")
        else:
            if not _nonempty_str(callout.get("title")):
                errors.append("content.final.callout.title이 비어 있다.")
            if not isinstance(callout.get("paragraphs"), list) or not callout["paragraphs"]:
                errors.append("content.final.callout.paragraphs는 1개 이상이어야 한다.")
        if not isinstance(final.get("tags"), list):
            errors.append("content.final.tags는 list여야 한다.")

    # footnote
    if not _nonempty_str(content.get("footnote")):
        errors.append("content.footnote가 비어 있다.")


# ---------------------------------------------------------------------------
# Quality validation
# ---------------------------------------------------------------------------

def _validate_quality(
    content: dict[str, Any],
    *,
    evidence_tools: list[str],
    errors: list[str],
) -> None:
    strings = _collect_strings(content)

    # Total visible text
    total_chars = sum(len(s) for s in strings)
    if total_chars < _MIN_VISIBLE_TEXT_CHARS:
        errors.append(
            f"전체 텍스트가 {total_chars}자로 너무 짧다 (최소 {_MIN_VISIBLE_TEXT_CHARS}자 필요). "
            "각 섹션의 본문을 더 구체적으로 작성하라."
        )

    # Overlong single text blocks
    overlong = [s for s in strings if len(s) > MAX_VISIBLE_TEXT_SEGMENT_CHARS]
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
