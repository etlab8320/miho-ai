"""Adapter for official university formula sidecar plugins."""

from __future__ import annotations

from typing import Any

from .db import db_path
from .grade_engine import _norm_subject_area, _subject_area_from_row
from .utils import _first_number


_FORMULA_MODULE: Any = None
_FORMULA_LOAD_FAILED = False


def _formula_module() -> Any:
    global _FORMULA_MODULE, _FORMULA_LOAD_FAILED
    if _FORMULA_MODULE is not None or _FORMULA_LOAD_FAILED:
        return _FORMULA_MODULE
    import importlib.util
    import sys

    formula_dir = db_path().parent
    entry = formula_dir / "susi27_university_formula_plugins.py"
    if not entry.exists():
        _FORMULA_LOAD_FAILED = True
        return None
    try:
        if str(formula_dir) not in sys.path:
            sys.path.insert(0, str(formula_dir))
        spec = importlib.util.spec_from_file_location("susi27_university_formula_plugins", entry)
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("susi27_university_formula_plugins", module)
        spec.loader.exec_module(module)
        _FORMULA_MODULE = module
    except Exception:
        _FORMULA_LOAD_FAILED = True
        return None
    return _FORMULA_MODULE


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _formula_calculate(
    university: str,
    merged_row: dict[str, Any],
    grades: list[dict[str, Any]],
    attendance: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    module = _formula_module()
    if module is None:
        return None
    fn = (getattr(module, "REGISTRY", None) or {}).get(university)
    if fn is None:
        return None
    # 대학 요강 표준: 진로선택과목만 성취도(A/B/C)→등급 환산해 반영하고, 일반선택
    # 성취도평가 과목(과학탐구실험·사회탐구실험 등)은 석차등급이 없으면 반영하지 않는다
    # (2026-06-17 원광대 실사고: plugin이 course_type 구분 없이 achievement만 보고 일반선택
    # 성취도과목을 진로로 오반영 → car_avg 왜곡). 일반선택 성취도과목은 achievement를
    # plugin에 넘기지 않아(None) 진로 환산 풀에서 빼고, 석차등급으로만 반영되게 한다.
    def _ach_for_plugin(g: dict[str, Any]) -> str | None:
        ach = g.get("성취도")
        if not ach:
            return None
        ctype = str(g.get("과목구분") or g.get("과목유형") or g.get("course_type") or "").strip()
        area = _norm_subject_area(g.get("교과") or g.get("area") or g.get("subject_area"))
        if ctype == "일반선택" and not _int_or_none(g.get("등급")):
            if university == "강원대학교" and area == "체육":
                return str(ach)
            return None
        return str(ach)
    ratio_keys = (
        "achievement_a_ratio",
        "a_ratio",
        "achievement_ab_ratio",
        "ab_ratio",
        "achievement_abc_ratio",
        "abc_ratio",
        "student_ratio",
        "achievement_ratio",
        "achievement_ratios",
        "grade_scale",
        "등급체계",
        "석차등급제",
    )
    transcript = []
    for g in grades:
        if not isinstance(g, dict):
            continue
        category = _subject_category_for_plugin(g)
        record = module.SubjectRecord(
            grade=_int_or_none(g.get("학년")) or 0,
            semester=_int_or_none(g.get("학기")) or 0,
            category=category,
            subject=str(g.get("과목") or ""),
            credit=float(_first_number(g.get("이수단위")) or 1.0),
            rank_grade=_int_or_none(g.get("등급")),
            achievement=_ach_for_plugin(g),
            raw_score=_first_number(g.get("원점수")),
            mean_score=_first_number(g.get("평균")),
            standard_deviation=_first_number(g.get("표준편차")),
            course_type=str(g.get("과목구분") or g.get("과목유형") or g.get("course_type") or ""),
        )
        for key in ratio_keys:
            if key in g:
                setattr(record, key, g.get(key))
        transcript.append(record)
    try:
        result = fn(merged_row, transcript, attendance or {})
    except Exception:
        return None
    data = result.to_dict() if hasattr(result, "to_dict") else None
    if not isinstance(data, dict):
        return None
    return data


def _subject_category_for_plugin(row: dict[str, Any]) -> str:
    resolved = _subject_area_from_row(row)
    if resolved and resolved not in {"기타", "일반", "공통", "선택"}:
        return resolved
    return str(row.get("교과") or "")


def _official_selected_academic_subjects(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary_categories = {
        "교과",
        "1단계",
        "출결",
        "출결감점",
        "출석",
        "봉사",
        "학생부",
        "학생부교과",
        "학업역량평가",
        "실기",
        "면접",
        "서류",
        "진로",
        "학교폭력",
        "환산",
        "환산점수",
        "부족교과",
        "비교과/실기",
    }
    academic: list[dict[str, Any]] = []
    for item in selected:
        category = str(item.get("category") or "").strip()
        if category in summary_categories:
            continue
        nested_rows = item.get("rows")
        if isinstance(nested_rows, list) and nested_rows:
            academic.extend(row for row in nested_rows if isinstance(row, dict))
        else:
            academic.append(item)
    return academic
