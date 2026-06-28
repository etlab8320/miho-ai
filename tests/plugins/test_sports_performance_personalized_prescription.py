"""Tests for student-specific sports prescription selection."""

from __future__ import annotations

from typing import Any

from plugins.sports_performance.feedback_tool import feedback_tool_handler
from plugins.sports_performance.exercise_library import (
    exercise_library_entries,
    exercise_library_target_counts,
    exercise_library_variable_counts,
)
from plugins.sports_performance.report_html import build_sports_report_html_payload, render_sports_report_html


def _variable(key: str, current: float, elite: float, unit: str) -> dict[str, Any]:
    return {
        "variable_key": key,
        "variable_value": current,
        "elite_1pct": f"{elite} {unit}",
        "unit": unit,
        "measured_at": "2026-06-28",
    }


def _report(*variables: dict[str, Any]) -> dict[str, Any]:
    return build_sports_report_html_payload(
        {
            "exercise": "제멀",
            "student": {"name": "강지연", "gender": "여", "academy": "일산"},
            "record": {"current": "218 cm", "previous": "214 cm", "change": "+4 cm"},
            "variables": list(variables),
            "feedback": {"reviewer": {"status": "pass"}},
        }
    )


def test_prescription_changes_by_variable_deficit_cluster() -> None:
    horizontal_deficit = _report(
        _variable("takeoff_angle", 20.1, 24.6, "deg"),
        _variable("horizontal_velocity", 3.82, 4.78, "m/s"),
        _variable("takeoff_transition_time", 0.24, 0.23, "s"),
    )
    transition_deficit = _report(
        _variable("takeoff_angle", 24.1, 24.6, "deg"),
        _variable("horizontal_velocity", 4.64, 4.78, "m/s"),
        _variable("takeoff_transition_time", 0.43, 0.23, "s"),
        _variable("descent_velocity", 1.18, 1.92, "m/s"),
    )

    horizontal_blocks = horizontal_deficit["training_program"]["exercise_blocks"]
    transition_blocks = transition_deficit["training_program"]["exercise_blocks"]
    horizontal_strength = horizontal_deficit["training_program"]["strength_blocks"]
    transition_strength = transition_deficit["training_program"]["strength_blocks"]

    assert horizontal_blocks[0]["title"] == "앞으로 밀어 멀리뛰기"
    assert transition_blocks[0]["title"] == "앉았다 바로 점프하기"
    assert horizontal_blocks[0]["student_reason"] != transition_blocks[0]["student_reason"]
    for report in (horizontal_deficit, transition_deficit):
        main_targets = {
            block["target"]
            for block in report["training_program"]["exercise_library_blocks"][:3]
        }
        support_targets = {
            block["target"]
            for block in report["training_program"]["strength_blocks"]
        }
        assert main_targets.isdisjoint(support_targets)
    assert "3.82 m/s" in horizontal_blocks[0]["student_reason"]
    assert "0.43 s" in transition_blocks[0]["student_reason"]


def test_variable_rows_explain_direction_gap_and_student_fault() -> None:
    report = _report(
        _variable("takeoff_angle", 20.1, 24.6, "deg"),
        _variable("horizontal_velocity", 3.82, 4.78, "m/s"),
    )
    rows = {
        variable["key"]: variable
        for group in report["variable_groups"]
        for variable in group["variables"]
    }

    assert rows["takeoff_angle"]["status"] == "목표보다 낮음"
    assert rows["takeoff_angle"]["gap"] == "-4.50 deg"
    assert "너무 낮게 나가" in rows["takeoff_angle"]["diagnosis"]
    assert rows["horizontal_velocity"]["status"] == "상위 모델보다 느림"
    assert "앞으로 미는 속도" in rows["horizontal_velocity"]["diagnosis"]


def test_signed_speed_and_angle_variables_use_magnitude_for_coaching() -> None:
    report = _report(
        _variable("arm_backswing_angle", -73.51, -133.78, "°"),
        _variable("descent_velocity", -1.05, -1.16, "m/s"),
    )
    rows = {
        variable["key"]: variable
        for group in report["variable_groups"]
        for variable in group["variables"]
    }

    assert rows["arm_backswing_angle"]["current"] == "73.51 °"
    assert rows["arm_backswing_angle"]["elite_1pct"] == "133.78 °"
    assert rows["arm_backswing_angle"]["gap"] == "-60.27 °"
    assert rows["arm_backswing_angle"]["status"] == "목표보다 낮음"
    assert rows["descent_velocity"]["current"] == "1.05 m/s"
    assert rows["descent_velocity"]["elite_1pct"] == "1.16 m/s"
    assert rows["descent_velocity"]["gap"] == "-0.11 m/s"
    assert rows["descent_velocity"]["status"] == "상위 모델보다 느림"


def test_report_extracts_strength_variables_separately_from_bottlenecks() -> None:
    report = _report(
        _variable("horizontal_velocity", 5.48, 4.76, "m/s"),
        _variable("takeoff_transition_time", 0.17, 0.33, "s"),
        _variable("takeoff_angle", 7.87, 11.66, "°"),
        _variable("arm_backswing_angle", -73.51, -133.78, "°"),
    )

    strength_titles = [item["title"] for item in report["strengths"]]
    bottleneck_titles = [item["title"] for item in report["bottlenecks"]]

    assert "앞으로 나가는 속도" in strength_titles
    assert "앉았다 밀고 나가기까지 걸린 시간" in strength_titles
    assert "뛰어오르는 각도" not in strength_titles
    assert "뛰어오르는 각도" in bottleneck_titles
    assert report["strengths"][0]["status"] in {"상위 모델보다 빠름", "상위 모델보다 짧음"}
    assert all(item["current"] for item in report["strengths"])
    assert all(item["elite_1pct"] for item in report["strengths"])
    assert all(item["gap"] for item in report["strengths"])


def test_personalized_strength_blocks_are_rendered_in_html() -> None:
    html = render_sports_report_html(
        {
            "exercise": "제멀",
            "student": {"name": "강지연", "gender": "여", "academy": "일산"},
            "record": {"current": "218 cm"},
            "variables": [
                _variable("takeoff_angle", 20.1, 24.6, "deg"),
                _variable("horizontal_velocity", 3.82, 4.78, "m/s"),
            ],
            "feedback": {"reviewer": {"status": "pass"}},
        }
    )

    assert "스플릿 스쿼트와 수평 푸시 보강" in html
    assert "현재 3.82 m/s" in html
    assert "앞으로 미는 속도" in html


def test_prescription_selects_combo_exercises_with_verified_video() -> None:
    report = _report(
        _variable("arm_backswing_angle", 98.1, 56.86, "°"),
        _variable("arm_swing_peak_velocity", 754.04, 914.2, "°/s"),
        _variable("knee_peak_angular_velocity", 616.38, 719.77, "°/s"),
    )

    library_blocks = report["training_program"]["exercise_library_blocks"]
    top_block = library_blocks[0]

    assert len(library_blocks) >= 5
    assert len(top_block["linked_variables"]) >= 2
    assert top_block["video"]["url"].startswith("https://www.youtube.com/watch?v=")
    assert top_block["video"]["verified_at"]
    assert top_block["video"]["verification"] == "yt-dlp metadata + ffmpeg frame audit"
    assert top_block["method_steps"]
    assert "현재" in top_block["selection_reason"]


def test_standing_long_jump_library_has_five_candidates_per_target() -> None:
    counts = exercise_library_target_counts("standing_long_jump")

    assert counts["arm_swing"] >= 5
    assert counts["hip_drive"] >= 5
    assert counts["transition_speed"] >= 5
    assert counts["horizontal_velocity_loss"] >= 5
    assert counts["takeoff_result"] >= 5
    assert counts["landing_efficiency"] >= 5


def test_standing_long_jump_library_has_five_candidates_per_variable() -> None:
    counts = exercise_library_variable_counts("standing_long_jump")
    expected_variables = {
        "takeoff_angle",
        "horizontal_velocity",
        "vertical_velocity",
        "takeoff_transition_time",
        "descent_velocity",
        "com_descent_distance",
        "hip_peak_angular_velocity",
        "knee_peak_angular_velocity",
        "ankle_peak_angular_velocity",
        "hip_takeoff_angle",
        "knee_takeoff_angle",
        "ankle_takeoff_angle",
        "arm_backswing_angle",
        "arm_swing_peak_velocity",
        "com_foot_distance",
        "flight_hip_min_angle",
        "flight_knee_min_angle",
    }

    assert {key for key in expected_variables if counts.get(key, 0) < 5} == set()


def test_standing_long_jump_library_avoids_machine_based_exercises() -> None:
    forbidden_terms = (
        "machine",
        "머신",
        "seated leg curl",
        "treadmill",
        "back handspring",
        "tuck jump",
        "r4hkxmcp",
        "banded arm drive",
        "sport hq",
        "long jump arm action",
        "triple jump",
        "titleist",
        "clubhead",
        "howcast",
        "25 tips & drills for coaching horizontal jumps",
        "resisted hip hinge pre jump drill",
        "john shepherd",
        "jeff nippard",
    )
    text = str(exercise_library_entries("standing_long_jump")).lower()

    assert all(term not in text for term in forbidden_terms)
    assert "towel hamstring curls" in text
    assert "broad jump stick landing" in text
    assert "standing long jump with arm swing" in text
    assert "hip hinge: broad jump analogy" in text
    assert "dumbbell romanian (rdl) deadlift" in text


def test_prescription_library_changes_for_different_deficit_clusters() -> None:
    arm_report = _report(
        _variable("arm_backswing_angle", 98.1, 56.86, "°"),
        _variable("arm_swing_peak_velocity", 754.04, 914.2, "°/s"),
    )
    hip_report = _report(
        _variable("hip_peak_angular_velocity", 650.11, 708.35, "°/s"),
        _variable("horizontal_velocity", 4.01, 4.76, "m/s"),
    )

    arm_titles = [block["title"] for block in arm_report["training_program"]["exercise_library_blocks"][:3]]
    hip_titles = [block["title"] for block in hip_report["training_program"]["exercise_library_blocks"][:3]]

    assert arm_titles != hip_titles
    assert any("팔" in title or "메디신볼" in title for title in arm_titles)
    assert any("엉덩이" in title or "수평" in title or "힌지" in title for title in hip_titles)


def test_arm_swing_priority_uses_jump_specific_video() -> None:
    report = _report(
        _variable("arm_backswing_angle", 84.46, 133.78, "°"),
        _variable("arm_swing_peak_velocity", 937.43, 1001.73, "°/s"),
    )

    top_block = report["training_program"]["exercise_library_blocks"][0]

    assert top_block["title"] == "제멀 팔스윙 리듬 보정"
    assert top_block["video"]["title"] == "Standing Long Jump With Arm Swing"
    assert top_block["video"]["channel"] == "Nicole W"


def test_priority_prescription_uses_corrective_exercises_not_event_repetition() -> None:
    report = _report(
        _variable("ankle_peak_angular_velocity", 479.53, 685.19, "°/s"),
        _variable("ankle_takeoff_angle", 102.23, 118.6, "°"),
        _variable("hip_takeoff_angle", 159.53, 177.05, "°"),
        _variable("flight_hip_min_angle", 25.82, 44.91, "°"),
        _variable("com_foot_distance", 62.14, 70.42, "cm"),
    )

    top_blocks = report["training_program"]["exercise_library_blocks"][:3]
    top_titles = " ".join(block["title"] for block in top_blocks)
    top_kinds = {block["kind"] for block in top_blocks}
    linked_keys = {
        variable["key"]
        for block in top_blocks
        for variable in block["linked_variables"]
    }

    assert "event_drill" not in top_kinds
    assert {"static_corrective", "dynamic_corrective"}.issubset(top_kinds)
    assert "발목" in top_titles
    assert "제멀" not in top_titles
    assert "멀리뛰기" not in top_titles
    assert "ankle_peak_angular_velocity" in linked_keys
    assert "ankle_takeoff_angle" in linked_keys


def test_point_support_does_not_repeat_main_priority_targets() -> None:
    report = _report(
        _variable("ankle_peak_angular_velocity", 479.53, 685.19, "°/s"),
        _variable("ankle_takeoff_angle", 102.23, 118.6, "°"),
        _variable("hip_takeoff_angle", 159.53, 177.05, "°"),
        _variable("flight_hip_min_angle", 25.82, 44.91, "°"),
        _variable("com_foot_distance", 62.14, 70.42, "cm"),
    )

    main_targets = {
        block["target"]
        for block in report["training_program"]["exercise_library_blocks"][:3]
    }
    support_targets = {
        block["target"]
        for block in report["training_program"]["strength_blocks"]
    }
    support_titles = " ".join(block["title"] for block in report["training_program"]["strength_blocks"])

    assert main_targets.isdisjoint(support_targets)
    assert "수건 햄스트링 컬" not in support_titles
    assert "발목-무릎 빠른 신전 점프 스쿼트" not in support_titles


def test_report_renders_exercise_library_video_and_method_page() -> None:
    html = render_sports_report_html(
        {
            "exercise": "제멀",
            "student": {"name": "강지연", "gender": "여", "academy": "일산"},
            "record": {"current": "218 cm"},
            "variables": [
                _variable("arm_backswing_angle", 98.1, 56.86, "°"),
                _variable("arm_swing_peak_velocity", 754.04, 914.2, "°/s"),
            ],
            "feedback": {"reviewer": {"status": "pass"}},
        }
    )

    assert "보강운동 라이브러리" in html
    assert "영상" in html
    assert "https://www.youtube.com/watch?v=" in html


def test_report_renders_corrective_labels_for_priority_prescription() -> None:
    html = render_sports_report_html(
        {
            "exercise": "제멀",
            "student": {"name": "이호근", "gender": "남", "academy": "일산"},
            "record": {"current": "245 cm"},
            "variables": [
                _variable("ankle_peak_angular_velocity", 479.53, 685.19, "°/s"),
                _variable("ankle_takeoff_angle", 102.23, 118.6, "°"),
                _variable("hip_takeoff_angle", 159.53, 177.05, "°"),
                _variable("flight_hip_min_angle", 25.82, 44.91, "°"),
                _variable("com_foot_distance", 62.14, 70.42, "cm"),
            ],
            "feedback": {"reviewer": {"status": "pass"}},
        }
    )

    assert "정적 보강" in html
    assert "동적 보강" in html
    assert "발목-무릎 빠른 신전 점프 스쿼트" in html


def test_feedback_understands_max_variable_keys_not_only_legacy_aliases() -> None:
    payload = feedback_tool_handler(
        {
            "student_name": "강지연",
            "exercise": "제멀",
            "metrics": {
                "takeoff_angle": 20.1,
                "horizontal_velocity": 3.82,
                "takeoff_transition_time": 0.43,
            },
        }
    )

    assert "이륙각" in payload
    assert "수평속도" in payload
    assert "전환시간" in payload
