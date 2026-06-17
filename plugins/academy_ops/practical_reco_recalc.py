"""Official score recalculation guard for practical recommendation PDFs."""

from __future__ import annotations

import re
from typing import Any

from .practical_reco_schema import _first_number
from ..susi_ops.service import recommend_candidates


_FIELD_CHECKS = (
    ("converted", "student_record_score", "내신환산"),
    ("max_total", "max_possible_total", "실기만점 합산"),
    ("first_cut", "prev_first_total", "전년도 최초합"),
    ("final_cut", "prev_final_total", "전년도 최종합"),
)


def validate_recalculated_scores(
    student_name: str,
    content: dict[str, Any],
) -> tuple[bool, list[str], dict[str, Any]]:
    """Validate PDF row scores against the official susi recommendation output."""
    rows = ((content.get("comparison") or {}).get("rows") or [])
    checks: dict[str, Any] = {"recalculated_rows": 0}
    if not isinstance(rows, list) or not rows:
        return True, [], checks

    clean_student = str(student_name or "").strip()
    if not clean_student:
        return False, ["student_name이 비어 있어 공식 산식 재검산을 할 수 없다."], checks

    try:
        result = recommend_candidates(clean_student, region="전국", max_candidates=400)
    except Exception as exc:  # noqa: BLE001
        return False, [f"공식 산식 재검산 호출 실패: {exc}"], checks

    if result.get("error"):
        return False, [f"공식 산식 재검산 실패: {result['error']}"], checks

    candidates = result.get("candidates") or []
    if not isinstance(candidates, list):
        candidates = []

    errors: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        candidate = _find_candidate(row, candidates)
        if candidate is None:
            extra_candidates = _row_candidates(clean_student, row)
            candidates.extend(extra_candidates)
            candidate = _find_candidate(row, extra_candidates)
        label = _row_label(row, index)
        if candidate is None:
            errors.append(
                f"{label}: 공식 재산출 후보에서 같은 학교·학과·전형을 찾지 못했다. "
                "요강 산식으로 산출된 susi27 추천 후보만 PDF에 실을 수 있다."
            )
            continue
        checks["recalculated_rows"] += 1
        for row_field, candidate_field, korean_label in _FIELD_CHECKS:
            _check_score_field(
                errors,
                label=label,
                row_field=row_field,
                korean_label=korean_label,
                actual_value=row.get(row_field),
                expected_value=candidate.get(candidate_field),
            )

    return not errors, errors, checks


def _row_candidates(student_name: str, row: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        result = recommend_candidates(
            student_name,
            university=str(row.get("school") or "").strip() or None,
            department=str(row.get("department") or "").strip() or None,
            admission_track=_track_search_term(row.get("track")),
            region="전국",
            max_candidates=20,
        )
    except Exception:  # noqa: BLE001
        return []
    candidates = result.get("candidates") or []
    return candidates if isinstance(candidates, list) else []


def _find_candidate(row: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    row_uid = _clean(row.get("university_id") or row.get("school_id"))
    if row_uid:
        for candidate in candidates:
            if _clean(candidate.get("university_id")) == row_uid:
                return candidate

    row_school = _normalize(row.get("school"))
    row_department = _normalize(row.get("department"))
    row_track = _normalize_track(row.get("track"))
    for candidate in candidates:
        if row_school != _normalize(candidate.get("university")):
            continue
        if row_department != _normalize(candidate.get("department")):
            continue
        candidate_track = _normalize_track(candidate.get("admission_track"))
        if _track_matches(row_track, candidate_track):
            return candidate
    return None


def _check_score_field(
    errors: list[str],
    *,
    label: str,
    row_field: str,
    korean_label: str,
    actual_value: Any,
    expected_value: Any,
) -> None:
    actual = _first_number(actual_value)
    expected = _first_number(expected_value)
    if expected is None:
        if actual is not None:
            errors.append(
                f"{label}: {korean_label}({row_field})은 공식 산출값이 없으므로 '-'로 둬야 한다 "
                f"(현재 {actual:g})."
            )
        return
    if actual is None:
        errors.append(
            f"{label}: {korean_label}({row_field}) 숫자가 없다. 공식 산출값 {expected:g}와 일치해야 한다."
        )
        return
    if abs(actual - expected) > 0.01:
        errors.append(
            f"{label}: {korean_label}({row_field})이 공식 산출값과 다르다 "
            f"(PDF {actual:g}, 공식 {expected:g})."
        )


def _row_label(row: dict[str, Any], index: int) -> str:
    school = str(row.get("school") or "").strip() or "학교명 없음"
    department = str(row.get("department") or "").strip() or "학과명 없음"
    track = str(row.get("track") or "").strip() or "전형명 없음"
    return f"comparison.rows[{index}] {school} {department} {track}"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize(value: Any) -> str:
    return re.sub(r"[\s·/(),._-]+", "", str(value or "").lower())


def _normalize_track(value: Any) -> str:
    text = str(value or "").split("·", 1)[0]
    return _normalize(text)


def _track_search_term(value: Any) -> str | None:
    text = str(value or "").split("·", 1)[0].strip()
    return text or None


def _track_matches(row_track: str, candidate_track: str) -> bool:
    if not row_track or not candidate_track:
        return row_track == candidate_track
    return row_track == candidate_track or row_track in candidate_track or candidate_track in row_track
