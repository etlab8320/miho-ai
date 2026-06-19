"""Compatibility façade for the 2027 수시 calculation plugin.

The implementation is split by concern; this module re-exports the public API
and legacy private helpers used by existing tests and plugin imports.
"""

from __future__ import annotations

from .calculation import calculate_score, _is_calculable_confidence, _is_verified_confidence
from .db import DEFAULT_DB, _connect, _json_loads, _like, db_path
from .formula_adapter import (
    _formula_calculate,
    _formula_module,
    _int_or_none,
    _official_selected_academic_subjects,
)
from .grade_engine import (
    _grade_value,
    _is_regular_subject,
    _missing_achievement_ratio_inputs,
    _norm_subject_area,
    _score_from_grade_table,
    _subject_allowed,
    _unit_value,
    _weighted_average_grade,
    _within_semester_limit,
)
from .prev_year import _safe_like_term, _vultr_mysql, _vs_prev_year, lookup_prev_year
from .recommendation import (
    _parse_regions,
    _region_map,
    _school_tier,
    _school_tier_map,
    _student_grades_from_central,
    _track_cuts,
    recommend_candidates,
)
from .rules import _minimum_csat, lookup_rules
from .utils import _first_number, _optional_positive_int

__all__ = [
    "DEFAULT_DB",
    "_connect",
    "_first_number",
    "_formula_calculate",
    "_formula_module",
    "_grade_value",
    "_int_or_none",
    "_is_calculable_confidence",
    "_is_regular_subject",
    "_is_verified_confidence",
    "_json_loads",
    "_like",
    "_minimum_csat",
    "_missing_achievement_ratio_inputs",
    "_norm_subject_area",
    "_official_selected_academic_subjects",
    "_optional_positive_int",
    "_parse_regions",
    "_region_map",
    "_safe_like_term",
    "_school_tier",
    "_school_tier_map",
    "_score_from_grade_table",
    "_student_grades_from_central",
    "_subject_allowed",
    "_track_cuts",
    "_unit_value",
    "_vultr_mysql",
    "_vs_prev_year",
    "_weighted_average_grade",
    "_within_semester_limit",
    "calculate_score",
    "db_path",
    "lookup_prev_year",
    "lookup_rules",
    "recommend_candidates",
]
