"""Tests for sports performance report template contracts."""

from __future__ import annotations

import json

from plugins.sports_performance.report_templates import (
    build_report_template_response,
    report_template_tool_handler,
)


def test_standing_long_jump_template_contains_core_variable_groups() -> None:
    result = build_report_template_response({"exercise": "제멀"})
    template = result["template"]
    groups = {group["group_key"]: group for group in template["variable_groups"]}

    assert result["ok"] is True
    assert template["template_key"] == "standing_long_jump_v1"
    assert {"takeoff_result", "propulsion_chain", "countermovement_arm", "landing_efficiency"} <= set(groups)
    assert [group["priority"] for group in template["variable_groups"]] == [1, 2, 3, 4]
    assert {item["key"] for item in groups["takeoff_result"]["variables"]} == {
        "takeoff_angle",
        "horizontal_velocity",
        "vertical_velocity",
        "takeoff_transition_time",
    }
    assert all(item["direction"] for group in template["variable_groups"] for item in group["variables"])
    assert all(item["prescription_targets"] for group in template["variable_groups"] for item in group["variables"])


def test_templates_use_national_gender_elite_comparison_not_branch_top() -> None:
    result = build_report_template_response({"exercise": "standing_long_jump"})
    template = result["template"]

    assert template["comparison_layers"] == [
        "student_latest_vs_student_previous",
        "student_latest_vs_national_gender_elite_1pct",
        "student_latest_vs_national_gender_elite_5pct",
    ]
    assert not any("branch" in layer for layer in template["comparison_layers"])


def test_three_event_templates_use_local_references_as_primary_evidence() -> None:
    for exercise in ("제멀", "왕복달리기", "메디신볼"):
        result = build_report_template_response({"exercise": exercise})
        template = result["template"]
        refs = [ref for group_refs in template["reference_groups"].values() for ref in group_refs]

        assert result["ok"] is True
        assert template["source_policy"]["primary_evidence"] == "sports_local_reference"
        assert refs
        assert all(ref["ref"].startswith("sports_ref:") for ref in refs)


def test_template_contains_pdf_sections_and_prescription_contract() -> None:
    result = json.loads(report_template_tool_handler({"exercise": "제자리멀리뛰기"}))
    template = result["template"]
    pdf_sections = [section["section"] for section in template["pdf_contract"]]
    prescriptions = template["prescription_library"]

    assert pdf_sections == [
        "cover",
        "record_trend",
        "cohort_position",
        "variable_scorecard",
        "bottleneck_analysis",
        "prescription",
        "evidence",
        "review",
    ]
    assert {item["target"] for item in prescriptions} >= {
        "takeoff_result",
        "horizontal_velocity_loss",
        "transition_speed",
        "hip_drive",
        "arm_swing",
        "landing_efficiency",
    }
    assert all(item["drills"] for item in prescriptions)
    assert all(item["evidence_groups"] for item in prescriptions)
    assert template["llm_validation_contract"]["requires_variable_direction"] is True
    assert template["llm_validation_contract"]["requires_evidence_link"] is True
    assert template["llm_validation_contract"]["requires_training_dosage"] is True
    assert template["llm_validation_contract"]["requires_multi_variable_effect_map"] is True


def test_shuttle_and_medicine_ball_templates_define_directional_variables_and_drills() -> None:
    shuttle = build_report_template_response({"exercise": "왕복달리기"})["template"]
    medicine = build_report_template_response({"exercise": "메디신볼던지기"})["template"]

    shuttle_vars = {
        variable["key"]: variable
        for group in shuttle["variable_groups"]
        for variable in group["variables"]
    }
    medicine_vars = {
        variable["key"]: variable
        for group in medicine["variable_groups"]
        for variable in group["variables"]
    }

    assert shuttle_vars["contact_time"]["direction"] == "lower_is_better"
    assert shuttle_vars["turn_angle"]["direction"] == "range_is_better"
    assert medicine_vars["release_angle"]["direction"] == "range_is_better"
    assert medicine_vars["trunk_rotation"]["direction"] == "higher_is_better"
    assert any(item["target"] == "contact_time" for item in shuttle["prescription_library"])
    assert any(item["target"] == "trunk_rotation" for item in medicine["prescription_library"])


def test_training_programs_define_weeks_frequency_sets_and_variable_effects() -> None:
    for exercise in ("제멀", "왕복달리기", "메디신볼"):
        template = build_report_template_response({"exercise": exercise})["template"]
        program = template["training_program"]
        blocks = program["exercise_blocks"]

        assert program["duration_weeks"] >= 4
        assert program["sessions_per_week"] >= 2
        assert program["session_minutes"] >= 30
        assert program["weekly_structure"]
        assert blocks
        assert any(len(block["primary_variables"]) + len(block["secondary_variables"]) >= 2 for block in blocks)
        for block in blocks:
            dosage = block["dosage"]
            assert block["drill_key"]
            assert block["title"]
            assert block["primary_variables"]
            assert block["expected_variable_effects"]
            assert block["evidence_groups"]
            assert dosage["weeks"] >= 4
            assert dosage["sessions_per_week"] >= 1
            assert dosage["sets"]
            assert dosage["reps_or_time"]
            assert dosage["rest_seconds"] > 0
            assert dosage["progression"]


def test_standing_long_jump_program_links_fast_reversal_to_multiple_variables() -> None:
    template = build_report_template_response({"exercise": "제멀"})["template"]
    blocks = {block["drill_key"]: block for block in template["training_program"]["exercise_blocks"]}
    block = blocks["fast_reversal_cmj"]
    affected = {effect["variable_key"] for effect in block["expected_variable_effects"]}

    assert {"takeoff_transition_time", "descent_velocity", "vertical_velocity"} <= affected
    assert block["dosage"]["sets"] == "5"
    assert "바로 뛰어오른다" in block["how_to"]


def test_template_rejects_unsupported_exercise_with_korean_error() -> None:
    result = build_report_template_response({"exercise": "좌전굴"})

    assert result["ok"] is False
    assert "제멀, 왕복달리기, 메디신볼" in result["errors"][0]
