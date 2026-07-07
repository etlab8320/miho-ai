"""Official 수시 score calculation service."""

from __future__ import annotations

import json
from typing import Any

from .attendance import score_attendance
from .db import _connect, _json_loads
from .formula_adapter import _formula_calculate, _official_selected_academic_subjects
from .grade_engine import (
    _missing_achievement_ratio_inputs,
    _score_from_grade_table,
    _weighted_average_grade,
)
from .prev_year import _vs_prev_year
from .rules import _minimum_csat
from .score_adjustments import apply_unit_shortfall_adjustment
from .semester_rules import is_graduate_context
from .utils import _first_number


# confidence 라벨은 검증 파이프라인이 진화하며 15종 이상으로 늘었다 (verified,
# official_verified, official_pdf_codex_verified, high, ...). 계산 가능 신뢰도는
# "verified" 포함 또는 "high"(검증 완료 high-confidence 룰)이며, 계산 불가 표식
# (non_calc/non_auto/absent/not_in_guide)이 붙은 건 제외한다. (2026-06-17 계명대 등
# high 신뢰 실기룰 29개가 계산 차단되던 것 수정.)
_NON_CALC_MARKERS = ("non_calc", "non_auto", "absent", "not_in_guide")
_CALC_OK_LABELS = ("verified", "high")


def _is_calculable_confidence(confidence: str | None) -> bool:
    text = str(confidence or "").lower()
    if not any(label in text for label in _CALC_OK_LABELS):
        return False
    return not any(marker in text for marker in _NON_CALC_MARKERS)


def _is_verified_confidence(confidence: str | None) -> bool:
    text = str(confidence or "").lower()
    return any(label in text for label in _CALC_OK_LABELS)


def _self_check_formula_key(calculation_test: Any) -> str | None:
    if not isinstance(calculation_test, dict):
        return None
    status_text = " ".join(
        str(calculation_test.get(key) or "").lower()
        for key in ("plugin_status", "plugin_self_check_status", "status")
    )
    if not any(token in status_text for token in ("ready", "passed", "calculated")):
        return None
    key = calculation_test.get("plugin_formula_key") or calculation_test.get("formula_key")
    return str(key).strip() if key else None


def calculate_score(
    university_id: str,
    grades: list[dict[str, Any]],
    attendance: dict[str, Any],
    practical_records: dict[str, Any],
    student_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM susi_calculation_rules WHERE university_id = ?",
        (university_id,),
    ).fetchone()

    if row is None:
        return {
            "university_id": university_id,
            "status": "missing_rule",
            "message": "아직 검증된 계산 룰이 없어. 요강 추출/검수 후 계산 가능.",
        }

    confidence = row["confidence"] or "unverified"
    score_logic = _json_loads(row["score_logic_json"], None)

    if not isinstance(score_logic, dict):
        return {
            "university_id": university_id,
            "status": "unverified_rule",
            "confidence": confidence,
            "message": "검증 완료된 산식이 아니어서 계산을 중단했어. 추측 계산은 하지 않음.",
        }

    readiness_text = str(score_logic.get("calculation_readiness") or "").lower()
    scope_text = str(score_logic.get("calculation_scope") or "").lower()
    manual_recommendation_override = (
        str(row["university_id"] or "") == "6"
        and "강릉캠퍼스" in str(row["university"] or "")
    )
    if manual_recommendation_override:
        readiness_text = "manual_recommendation_override"
        scope_text = "practical_recommendation"
        score_logic = dict(score_logic)
        score_logic["formula_key"] = "KANGWON_GANGNEUNG_LEGACY_PRACTICAL_RECORD300_PRACTICAL700"
    confidence_verified = _is_verified_confidence(confidence)
    confidence_calculable = True if manual_recommendation_override else _is_calculable_confidence(confidence)
    is_non_calculation_scope = (
        "non_calculation_track" in {readiness_text, scope_text}
        or "non_calculation_track" in readiness_text
        or "not_in_2027_official_guide" in {readiness_text, scope_text}
    )
    if not is_non_calculation_scope and not score_logic.get("formula_key"):
        fallback_key = _self_check_formula_key(_json_loads(row["calculation_test_json"], {},) or {})
        if fallback_key:
            score_logic = dict(score_logic)
            score_logic["formula_key"] = fallback_key
    has_formula_key = bool(score_logic.get("formula_key"))
    if is_non_calculation_scope and confidence_verified and not has_formula_key:
        return {
            "university_id": university_id,
            "status": "non_calculation_track",
            "confidence": confidence,
            "strategy": "non_calculation_rule",
            "formula_key": score_logic.get("formula_key") or score_logic.get("official_formula_key"),
            "message": "원문상 정량 교과 환산 대상이 아닌 전형이어서 계산하지 않음.",
            "stage_weights": score_logic.get("stage_weights") or {},
            "subject_flags": score_logic.get("subject_flags") or {},
            "semester_weights": score_logic.get("semester_weights") or {},
            "minimum_csat": _minimum_csat(score_logic, row["admission_meta_json"]),
            "attendance_seen": bool(attendance),
            "practical_records_seen": sorted(practical_records.keys()),
        }

    if not confidence_calculable and not has_formula_key:
        return {
            "university_id": university_id,
            "status": "unverified_rule",
            "confidence": confidence,
            "message": "검증 완료된 산식이 아니어서 계산을 중단했어. 추측 계산은 하지 않음.",
        }

    strategy = score_logic.get("strategy") or "weighted_grade_table"

    if score_logic.get("formula_key"):
        raw_row = conn.execute(
            "SELECT raw_json, source_status FROM db_university_rows WHERE university_id = ?",
            (university_id,),
        ).fetchone()
        raw_for_formula = _json_loads(raw_row["raw_json"] if raw_row else None, {}) or {}
        raw_for_formula["admission_track"] = row["admission_track"]
        raw_for_formula["department"] = row["department"]
        raw_for_formula["source_status"] = raw_row["source_status"] if raw_row else ""
        raw_for_formula["score_logic_json"] = json.dumps(score_logic, ensure_ascii=False)
        raw_for_formula["admission_meta_json"] = row["admission_meta_json"]
        raw_for_formula["attendance_logic_json"] = row["attendance_logic_json"]
        raw_for_formula["practical_events_json"] = row["practical_events_json"]
        formula_context = dict(attendance or {})
        if is_graduate_context(student_context):
            formula_context["is_graduate"] = True
            formula_context["include_grade3_semester2"] = True
        formula = _formula_calculate(row["university"], dict(raw_for_formula), grades, formula_context)
        if formula is not None and formula.get("status") == "ready":
            selected = formula.get("selected_subjects") or []
            academic_selected = _official_selected_academic_subjects(selected)
            record_score = float(formula["record_score"])
            result = {
                "university_id": university_id,
                "status": "calculated",
                "confidence": confidence,
                "strategy": "official_formula_plugin",
                "formula_key": formula.get("formula_key") or score_logic.get("formula_key"),
                "average_grade": formula.get("reflected_average_grade"),
                "used_subjects": len(academic_selected),
                "total_units": round(sum(float(s.get("credit") or 0.0) for s in academic_selected), 2),
                "student_record_score": round(record_score, 4),
                "record_full_score": _first_number(formula.get("record_full_score")),
                "practical_full_score": _first_number(formula.get("practical_full_score")),
                "full_practical_total": _first_number(formula.get("full_practical_total")),
                "stage_weights": score_logic.get("stage_weights") or {},
                "subject_flags": score_logic.get("subject_flags") or {},
                "semester_weights": score_logic.get("semester_weights") or {},
                "minimum_csat": _minimum_csat(score_logic, row["admission_meta_json"]),
                "attendance_seen": bool(attendance),
                "practical_records_seen": sorted(practical_records.keys()),
            }
            vs_prev = _vs_prev_year(conn, university_id, record_score)
            if vs_prev:
                plugin_total = _first_number(formula.get("full_practical_total"))
                if plugin_total is not None:
                    vs_prev["max_possible_total"] = round(plugin_total, 2)
                    plugin_non_record_max = _first_number(formula.get("practical_full_score"))
                    if plugin_non_record_max is not None:
                        vs_prev["practical_max"] = round(plugin_non_record_max, 2)
                    final_total = _first_number(vs_prev.get("prev_final_total"))
                    if final_total is not None:
                        vs_prev["reachable_at_full_practical"] = plugin_total >= final_total
                        if plugin_total < final_total:
                            practical_max = plugin_non_record_max
                            if practical_max is None:
                                practical_max = _first_number(vs_prev.get("practical_max")) or 0.0
                            vs_prev["warning"] = (
                                f"실기 만점({practical_max:g})을 받아도 합산 {plugin_total:g}점이 전년도 최종합 "
                                f"{final_total:g}점(올해 산식 환산)에 미달 — 이 학교는 상향으로도 추천 금지."
                            )
                        else:
                            vs_prev.pop("warning", None)
                result["vs_prev_year"] = vs_prev
            return result
        if formula is not None:
            response = {
                "university_id": university_id,
                "status": formula.get("status") or "strategy_not_implemented",
                "confidence": confidence,
                "strategy": "official_formula_plugin",
                "formula_key": formula.get("formula_key") or score_logic.get("formula_key"),
                "message": "원문상 정량 교과 환산 대상이 아닌 전형이어서 계산하지 않음.",
                "stage_weights": score_logic.get("stage_weights") or {},
                "subject_flags": score_logic.get("subject_flags") or {},
                "semester_weights": score_logic.get("semester_weights") or {},
                "minimum_csat": _minimum_csat(score_logic, row["admission_meta_json"]),
                "attendance_seen": bool(attendance),
                "practical_records_seen": sorted(practical_records.keys()),
            }
            for source_key, target_key in (
                ("record_score", "student_record_score"),
                ("record_full_score", "record_full_score"),
                ("practical_full_score", "practical_full_score"),
                ("full_practical_total", "full_practical_total"),
                ("reflected_average_grade", "average_grade"),
            ):
                value = _first_number(formula.get(source_key))
                if value is not None:
                    response[target_key] = value
            warnings = formula.get("warnings")
            if warnings:
                response["warnings"] = warnings
            return response
        if not confidence_calculable:
            return {
                "university_id": university_id,
                "status": "unverified_rule",
                "confidence": confidence,
                "strategy": "official_formula_plugin",
                "formula_key": score_logic.get("formula_key"),
                "message": "공식 산식 키는 있지만 실행 가능한 플러그인 결과가 없어 계산을 중단했어.",
            }

    if strategy != "weighted_grade_table":
        return {
            "university_id": university_id,
            "status": "strategy_not_implemented",
            "strategy": strategy,
            "message": "룰은 검증됐지만 이 산식 전략의 실행기가 아직 연결되지 않았어.",
            "inputs_seen": {
                "grades": len(grades),
                "attendance_keys": sorted(attendance.keys()),
                "practical_events": sorted(practical_records.keys()),
            },
        }

    missing_ratio_inputs = _missing_achievement_ratio_inputs(grades, score_logic, student_context)
    if missing_ratio_inputs:
        return {
            "university_id": university_id,
            "status": "missing_career_ratio_inputs",
            "confidence": confidence,
            "strategy": strategy,
            "message": "진로선택 B/C 성취도는 모집요강상 학생비율로 등급을 산출해야 해서 성취도별 학생비율 입력이 필요해.",
            "missing_subjects": missing_ratio_inputs,
        }

    average_grade, used_subjects, total_units, used_pool = _weighted_average_grade(
        grades, score_logic, student_context
    )

    if average_grade is None:
        return {
            "university_id": university_id,
            "status": "missing_grade_inputs",
            "confidence": confidence,
            "strategy": strategy,
            "message": "계산 가능한 룰은 있지만, 반영 교과/등급 입력이 부족해서 점수를 산출하지 못했어.",
            "input_rows": len(grades),
        }

    # 환산점수는 '과목별로 등급→점수 환산한 뒤 (단위)평균'한다 — 한국 대학 요강 표준
    # 산식(Σ 과목점수×단위 / Σ 단위). 비선형 점수표에서는 '평균등급→보간'과 결과가
    # 달라지므로(2026-06-17 한국해양대 실사고, 비선형 88개교 영향) 과목별 환산이 정답이다.
    # 선형 점수표 학교는 두 방식이 수학적으로 동일해 회귀 영향이 없다.
    # 단위가중/단순평균 여부는 학교마다 다르므로(한국해양대=단위가중, 세명대·청주대=단순)
    # credit_weighted 플래그를 그대로 따른다.
    grade_points = score_logic.get("grade_points") or {}
    _cw = score_logic.get("credit_weighted")
    _cw = True if _cw is None else bool(_cw)
    # band_score: 평균등급(단순)을 '구간→고정점수' 표에 매핑하는 학교(광주대 등).
    #  과목별 환산이 아니라 평균석차등급을 구간표에 대입한다. band_score는
    #  [{"max":1.00,"score":270},{"max":1.50,"score":240},...] 형식(max 이하 구간).
    band_score = score_logic.get("band_score")
    if isinstance(band_score, list) and band_score:
        bands = sorted(
            ({"max": _first_number(b.get("max")), "score": _first_number(b.get("score"))}
             for b in band_score if isinstance(b, dict)),
            key=lambda b: (b["max"] if b["max"] is not None else 99),
        )
        record_score = None
        for b in bands:
            if b["max"] is not None and average_grade <= b["max"] + 1e-9:
                record_score = b["score"]
                break
        if record_score is None and bands:
            record_score = bands[-1]["score"]
    else:
        _per_subject = []
        for _g, _u in used_pool:
            _s = _score_from_grade_table(_g, grade_points)
            if _s is None:
                _per_subject = None
                break
            _per_subject.append((_s, _u))
        if _per_subject:
            if _cw:
                _tu = sum(u for _, u in _per_subject)
                record_score = (sum(s * u for s, u in _per_subject) / _tu) if _tu > 0 else None
            else:
                record_score = sum(s for s, _ in _per_subject) / len(_per_subject)
        else:
            record_score = None

    if record_score is None:
        return {
            "university_id": university_id,
            "status": "missing_grade_table",
            "confidence": confidence,
            "strategy": strategy,
            "message": "평균등급은 계산했지만 등급별 환산점수표가 없어 최종 환산점수를 산출하지 못했어.",
            "average_grade": round(average_grade, 4),
            "minimum_csat": _minimum_csat(score_logic, row["admission_meta_json"]),
        }

    adjusted_score = apply_unit_shortfall_adjustment(record_score, total_units, score_logic)
    academic_record_score = adjusted_score
    record_score = academic_record_score
    attendance_logic = _json_loads(row["attendance_logic_json"], {}) or {}
    attendance_component = score_attendance(attendance_logic, attendance or {})
    if attendance_component:
        record_score += float(attendance_component["attendance_score"])
    practical_events = _json_loads(row["practical_events_json"], {}) or {}
    practical_full_score = _practical_full_score(practical_events)

    result = {
        "university_id": university_id,
        "status": "calculated",
        "confidence": confidence,
        "strategy": strategy,
        "average_grade": round(average_grade, 4),
        "used_subjects": used_subjects,
        "total_units": round(total_units, 2),
        "student_record_score": round(record_score, 4),
        "academic_record_score": round(academic_record_score, 4),
        "stage_weights": score_logic.get("stage_weights") or {},
        "subject_flags": score_logic.get("subject_flags") or {},
        "semester_weights": score_logic.get("semester_weights") or {},
        "minimum_csat": _minimum_csat(score_logic, row["admission_meta_json"]),
        "attendance_seen": bool(attendance),
        "practical_records_seen": sorted(practical_records.keys()),
    }
    if attendance_component:
        result.update(attendance_component)
        result["record_full_score"] = round(
            (_max_grade_point(score_logic.get("grade_points")) or academic_record_score)
            + float(attendance_component["attendance_full_score"]),
            4,
        )
    if practical_full_score is not None:
        result["practical_full_score"] = round(practical_full_score, 4)
        result["full_practical_total"] = round(record_score + practical_full_score, 4)
    vs_prev = _vs_prev_year(conn, university_id, record_score)
    if vs_prev:
        if practical_full_score is not None:
            vs_prev["practical_max"] = round(practical_full_score, 2)
            vs_prev["max_possible_total"] = round(record_score + practical_full_score, 2)
        result["vs_prev_year"] = vs_prev
    return result


def _practical_full_score(practical_events: Any) -> float | None:
    if not isinstance(practical_events, dict):
        return None
    for key in ("full_score", "practical_full_score", "max_score"):
        value = _first_number(practical_events.get(key))
        if value is not None and value >= 0:
            return value
    return None


def _max_grade_point(grade_points: Any) -> float | None:
    if not isinstance(grade_points, dict):
        return None
    values = [
        number
        for number in (_first_number(value) for value in grade_points.values())
        if number is not None
    ]
    return max(values) if values else None
