"""Accuracy contracts shared by academy admission tools."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


ACADEMY_ACCURACY_SCHEMA = "academy-accuracy/v1"


_ENGINE_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "key": "hakjong_report",
        "label": "학종 리포트",
        "engine_family": "hakjong",
        "canonical_tool": "academy_hakjong_report_package",
        "playbook_key": "academy_hakjong_report",
        "source_tools": [
            "life_record_lookup",
            "life_record_summary",
            "life_record_search",
            "hakjong_qualitative_profile",
            "hakjong_storm_prewrite",
            "susi27_rule_lookup",
        ],
        "required_axes": [
            "student_identity",
            "life_record_evidence",
            "hakjong_profile",
            "storm_prewrite",
            "susi_rule_context",
            "manifest_v2",
            "pdf_physical_validation",
            "media_delivery",
        ],
        "blocking_rules": [
            "do not use practical records as hakjong evidence",
            "do not deliver a report without manifest_v2 and physical PDF validation",
        ],
    },
    {
        "key": "susi_practical_all_candidates",
        "label": "수시 실기전형 전체 추천",
        "engine_family": "susi",
        "canonical_tool": "academy_practical_reco_all_candidates",
        "playbook_key": "academy_practical_recommendation",
        "source_tools": ["susi27_recommend_candidates"],
        "required_axes": [
            "student_identity",
            "region_scope",
            "single_pipeline",
            "practical_only",
            "full_practical_reachability",
            "no_truncated_candidates",
            "pdf_physical_validation",
        ],
        "blocking_rules": [
            "do not hand-assemble candidates from rule lookup plus score calls",
            "do not include schools unreachable at full practical score",
            "do not omit requested empty regions from the grouped report",
        ],
    },
    {
        "key": "susi_score_engine",
        "label": "수시 환산점수 계산",
        "engine_family": "susi",
        "canonical_tool": "susi27_score_calculate",
        "playbook_key": "susi_score_calculation",
        "source_tools": ["susi27_score_calculate"],
        "required_axes": [
            "student_subjects",
            "verified_rule",
            "formula_result",
            "score_breakdown",
            "vs_prev_year",
            "reachability_flag",
        ],
        "blocking_rules": [
            "do not invent score values without susi27_score_calculate output",
            "do not recommend an unreachable school as 상향",
        ],
    },
    {
        "key": "jungsi_score_engine",
        "label": "정시엔진 환산점수",
        "engine_family": "jungsi",
        "canonical_tool": "jungsi_student_university_score",
        "playbook_key": "",
        "source_tools": ["jungsi_student_university_score"],
        "required_axes": [
            "student_identity",
            "university_scope",
            "year",
            "exam",
            "score_breakdown",
            "comparison_year",
        ],
        "blocking_rules": [
            "do not use jungsi tools for hakjong or susi-practical decisions",
            "do not confirm a jungsi recommendation without score and comparison payload",
        ],
    },
)


def academy_accuracy_matrix() -> list[dict[str, Any]]:
    return [deepcopy(item) for item in _ENGINE_CONTRACTS]


def academy_accuracy_contract(engine_key: str) -> dict[str, Any] | None:
    key = str(engine_key or "").strip()
    for item in _ENGINE_CONTRACTS:
        if item["key"] == key:
            return deepcopy(item)
    return None


def build_accuracy_receipt(
    *,
    engine_key: str,
    source_tools: list[str],
    gates: dict[str, bool],
) -> dict[str, Any]:
    contract = academy_accuracy_contract(engine_key)
    if contract is None:
        return {
            "schema_version": ACADEMY_ACCURACY_SCHEMA,
            "status": "fail",
            "engine_key": str(engine_key or ""),
            "errors": ["unknown academy accuracy engine"],
        }

    normalized_gates = {str(key): bool(value) for key, value in gates.items()}
    required_axes = [str(axis) for axis in contract["required_axes"]]
    missing_axes = [axis for axis in required_axes if not normalized_gates.get(axis)]
    normalized_tools = [str(tool).strip() for tool in source_tools if str(tool).strip()]
    missing_tools = [
        tool for tool in contract["source_tools"] if tool not in set(normalized_tools)
    ]
    errors = [f"missing axis: {axis}" for axis in missing_axes]
    errors.extend(f"missing source tool: {tool}" for tool in missing_tools)

    return {
        "schema_version": ACADEMY_ACCURACY_SCHEMA,
        "status": "pass" if not errors else "fail",
        "engine_key": contract["key"],
        "engine_family": contract["engine_family"],
        "canonical_tool": contract["canonical_tool"],
        "source_tools": normalized_tools,
        "required_axes": required_axes,
        "gates": normalized_gates,
        "blocking_rules": list(contract["blocking_rules"]),
        "errors": errors,
    }


def validate_accuracy_matrix(matrix: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for item in matrix:
        key = str(item.get("key") or "").strip()
        if not key:
            errors.append("academy accuracy contract without key")
            continue
        if key in seen:
            errors.append(f"duplicate academy accuracy key: {key}")
        seen.add(key)
        for field in ("engine_family", "canonical_tool", "source_tools", "required_axes", "blocking_rules"):
            if not item.get(field):
                errors.append(f"{key} missing {field}")
        if len(item.get("required_axes") or []) < 4:
            errors.append(f"{key} has too few accuracy axes")
    return errors


def validate_accuracy_receipt(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if receipt.get("schema_version") != ACADEMY_ACCURACY_SCHEMA:
        errors.append("invalid academy accuracy schema")
    contract = academy_accuracy_contract(str(receipt.get("engine_key") or ""))
    if contract is None:
        errors.append("unknown academy accuracy engine")
        return errors
    if receipt.get("canonical_tool") != contract["canonical_tool"]:
        errors.append("canonical tool mismatch")
    gates = receipt.get("gates")
    if not isinstance(gates, dict):
        errors.append("gates must be a mapping")
        gates = {}
    for axis in contract["required_axes"]:
        if not gates.get(axis):
            errors.append(f"missing axis: {axis}")
    source_tools = set(receipt.get("source_tools") or [])
    for tool in contract["source_tools"]:
        if tool not in source_tools:
            errors.append(f"missing source tool: {tool}")
    if receipt.get("status") != ("pass" if not errors else "fail"):
        errors.append("status does not match receipt errors")
    return errors
