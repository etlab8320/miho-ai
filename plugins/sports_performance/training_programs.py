"""Multi-variable training program contracts for sports performance reports."""

from __future__ import annotations

from typing import Any


def training_program_for(exercise_key: str) -> dict[str, Any]:
    programs = {
        "standing_long_jump": _standing_long_jump_program,
        "shuttle_run": _shuttle_run_program,
        "medicine_ball_throw": _medicine_ball_throw_program,
    }
    builder = programs.get(exercise_key)
    return builder() if builder else {}


def _standing_long_jump_program() -> dict[str, Any]:
    return _program(
        "standing_long_jump_4w_multi_variable",
        "4주 동안 앉았다 뛰는 속도, 뛰어오르는 각도, 앞으로 미는 힘, 착지 자세를 함께 개선한다.",
        [
            _block(
                "fast_reversal_cmj",
                "앉았다 바로 점프하기",
                "transition_speed",
                ["takeoff_transition_time", "descent_velocity"],
                ["vertical_velocity", "com_descent_distance"],
                "무릎을 굽힌 뒤 바닥에서 멈추지 않고 바로 뛰어오른다. 많이 앉기보다 빨리 밀고 나오는 게 목표다.",
                ["countermovement"],
                sets="5",
                reps_or_time="3회",
                progression="1-2주는 얕게 앉아 빠르게 뛰고, 3-4주는 실제 제자리멀리뛰기 자세로 연결",
            ),
            _block(
                "horizontal_push_broad_jump",
                "앞으로 밀어 멀리뛰기",
                "horizontal_velocity_loss",
                ["horizontal_velocity", "takeoff_angle"],
                ["hip_peak_angular_velocity", "ankle_takeoff_angle"],
                "몸이 위로만 뜨지 않게 발로 바닥을 뒤로 밀어 앞으로 나가는 힘을 만든다.",
                ["biomechanics", "optimum_takeoff_angle"],
                sets="5",
                reps_or_time="3회",
                progression="1-2주 80% 거리, 3주 90%, 4주 실전 강도 3회만 수행",
            ),
            _block(
                "hip_drive_broad_jump",
                "엉덩이 힘으로 밀어 뛰기",
                "hip_drive",
                ["hip_peak_angular_velocity", "hip_takeoff_angle"],
                ["knee_peak_angular_velocity", "horizontal_velocity"],
                "무릎만 펴지 말고 엉덩이와 허벅지 뒤쪽으로 바닥을 밀어낸다.",
                ["biomechanics"],
                sets="4",
                reps_or_time="4회",
                progression="영상에서 엉덩이를 끝까지 펴는 타이밍이 맞으면 마지막 세트만 세게 수행",
            ),
            _block(
                "arm_swing_timing_jump",
                "팔 흔드는 타이밍 맞추기",
                "arm_swing",
                ["arm_backswing_angle", "arm_swing_peak_velocity"],
                ["takeoff_angle", "vertical_velocity"],
                "팔을 크게만 흔들지 말고 다리가 펴지는 순간에 맞춰 앞으로 빠르게 가져온다.",
                ["arm_swing"],
                sets="4",
                reps_or_time="4회",
                progression="팔을 못 쓰는 점프와 자유 점프를 번갈아 해 팔이 기록에 얼마나 보태는지 확인",
            ),
        ],
    )


def _shuttle_run_program() -> dict[str, Any]:
    return _program(
        "shuttle_run_4w_multi_variable",
        "4주 동안 발을 짧게 딛는 힘, 짧게 멈추는 힘, 낮은 자세, 다시 뛰는 첫걸음을 함께 개선한다.",
        [
            _block(
                "short_contact_cut_step",
                "발을 짧게 찍고 방향 바꾸기",
                "contact_time",
                ["contact_time", "turn_angle"],
                ["trunk_lean", "foot_contact_timing"],
                "발을 바닥에 오래 두지 말고 짧게 찍은 뒤 바로 다음 방향으로 밀어낸다.",
                ["change_of_direction", "foot_contact"],
                sets="5",
                reps_or_time="좌우 각 4회",
                progression="1-2주 정지형, 3-4주 접근속도를 올려 수행",
            ),
            _block(
                "deceleration_stick_reaccelerate",
                "짧게 멈추고 바로 다시 뛰기",
                "deceleration_control",
                ["deceleration_distance", "trunk_lean"],
                ["contact_time", "first_step_projection"],
                "멀리서 천천히 멈추지 말고 짧게 멈춘 뒤 첫걸음을 바로 진행 방향으로 낸다.",
                ["deceleration", "sprint_mechanics"],
                sets="4",
                reps_or_time="3회",
                progression="감속 거리를 줄이되 무릎/몸통이 무너지면 강도를 낮춤",
            ),
            _block(
                "three_step_exit_acceleration",
                "돌자마자 세 걸음 빠르게 나가기",
                "reacceleration",
                ["first_step_projection", "foot_contact_timing"],
                ["contact_time", "trunk_lean"],
                "방향을 바꾼 직후 세 걸음을 짧고 강하게 가져가 기록 손실을 줄인다.",
                ["sprint_mechanics"],
                sets="6",
                reps_or_time="1회 3보",
                progression="1-2주 70%, 3주 85%, 4주 실전 리듬으로 측정",
            ),
        ],
    )


def _medicine_ball_throw_program() -> dict[str, Any]:
    return _program(
        "medicine_ball_throw_4w_multi_variable",
        "4주 동안 공을 놓는 각도와 높이, 몸통 회전, 엉덩이 힘, 던지는 순서를 함께 개선한다.",
        [
            _block(
                "target_release_wall_throw",
                "벽 목표점 보고 던지기",
                "release_angle",
                ["release_angle", "release_height"],
                ["sequence_timing"],
                "벽에 목표점을 정하고 공을 놓는 각도와 높이가 매번 비슷하게 나오게 한다.",
                ["release_angle", "medicine_ball_power"],
                sets="5",
                reps_or_time="5회",
                progression="목표 높이를 유지한 채 거리와 공 속도만 점진 증가",
            ),
            _block(
                "hip_trunk_scoop_toss",
                "엉덩이와 몸통을 이어 던지기",
                "trunk_rotation",
                ["trunk_rotation", "hip_extension"],
                ["release_angle", "sequence_timing"],
                "엉덩이와 골반이 먼저 움직이고, 몸통이 따라온 뒤 팔이 마지막에 공을 보낸다.",
                ["medicine_ball_power"],
                sets="4",
                reps_or_time="6회",
                progression="1-2주 가벼운 공, 3-4주 실전 공으로 전환",
            ),
            _block(
                "step_rhythm_release",
                "발디딤과 던지는 타이밍 맞추기",
                "sequence_timing",
                ["sequence_timing", "release_height"],
                ["trunk_rotation", "hip_extension"],
                "다리, 몸통, 팔이 한꺼번에 나가지 않고 순서대로 이어지게 한다.",
                ["medicine_ball_power"],
                sets="5",
                reps_or_time="4회",
                progression="리듬이 깨지지 않을 때만 스텝 속도를 올린다.",
            ),
        ],
    )


def _program(program_key: str, objective: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "program_key": program_key,
        "duration_weeks": 4,
        "sessions_per_week": 3,
        "session_minutes": 45,
        "objective": objective,
        "weekly_structure": [
            "1주차: 기술 패턴 학습과 저강도 반복",
            "2주차: 같은 품질에서 반복 수 안정화",
            "3주차: 속도와 강도 점진 증가",
            "4주차: 실전 측정 리듬으로 전환",
        ],
        "exercise_blocks": blocks,
        "progression_rules": [
            "통증이 있으면 해당 블록 강도를 낮추고 코치 확인 후 진행한다.",
            "영상에서 자세가 무너지면 세트 수보다 품질을 우선한다.",
            "기록 측정은 피로 누적 전 세션 초반에 배치한다.",
        ],
    }


def _block(
    drill_key: str,
    title: str,
    target: str,
    primary_variables: list[str],
    secondary_variables: list[str],
    how_to: str,
    evidence_groups: list[str],
    *,
    sets: str,
    reps_or_time: str,
    progression: str,
) -> dict[str, Any]:
    method = _student_method(drill_key)
    return {
        "drill_key": drill_key,
        "title": title,
        "prescription_target": target,
        "primary_variables": primary_variables,
        "secondary_variables": secondary_variables,
        "how_to": how_to,
        "expected_variable_effects": [
            {"variable_key": key, "expected_direction": "toward_national_gender_elite_model"}
            for key in [*primary_variables, *secondary_variables]
        ],
        "student_setup": method["setup"],
        "student_steps": method["steps"],
        "coach_cue": method["cue"],
        "dosage": {
            "weeks": 4,
            "sessions_per_week": 2,
            "sets": sets,
            "reps_or_time": reps_or_time,
            "rest_seconds": 90,
            "intensity": "기술 품질이 유지되는 저-중강도",
            "progression": progression,
        },
        "evidence_groups": evidence_groups,
    }


def _student_method(drill_key: str) -> dict[str, Any]:
    methods: dict[str, dict[str, Any]] = {
        "fast_reversal_cmj": {
            "setup": "바닥에 표시선을 두고 양발을 골반 너비로 선다.",
            "steps": ["작게 앉는다.", "멈추지 말고 바로 위로 뛴다.", "착지 후 2초 동안 자세를 멈춘다."],
            "cue": "많이 앉지 말고 바로 튀어 나와.",
        },
        "horizontal_push_broad_jump": {
            "setup": "출발선 앞에 착지 목표선을 두고 70-80% 거리부터 시작한다.",
            "steps": ["팔과 엉덩이를 뒤로 준비한다.", "발로 바닥을 뒤로 긁듯이 민다.", "발을 앞으로 뻗고 무릎을 접어 착지한다."],
            "cue": "위로 뜨려고 하지 말고 바닥을 뒤로 밀어.",
        },
        "hip_drive_broad_jump": {
            "setup": "옆에서 영상을 찍어 엉덩이가 끝까지 펴지는지 본다.",
            "steps": ["엉덩이를 뒤로 접는다.", "가슴을 세운 채 엉덩이로 바닥을 민다.", "무릎보다 엉덩이가 먼저 펴지는 느낌으로 뛴다."],
            "cue": "무릎만 펴지 말고 엉덩이로 밀어.",
        },
        "arm_swing_timing_jump": {
            "setup": "팔 없이 1회, 팔 사용 1회를 번갈아 비교한다.",
            "steps": ["팔을 뒤로 준비한다.", "다리가 펴지는 순간 팔을 앞으로 보낸다.", "팔이 먼저 나가면 속도를 낮춰 다시 맞춘다."],
            "cue": "팔은 크게가 아니라 다리 펴질 때 맞춰.",
        },
    }
    return methods.get(
        drill_key,
        {
            "setup": "낮은 강도로 먼저 자세를 확인하고 기록 측정 전에는 피로를 남기지 않는다.",
            "steps": ["천천히 동작을 익힌다.", "자세가 맞으면 속도를 조금 올린다.", "무너지면 강도를 낮춘다."],
            "cue": "빠르게보다 정확하게 먼저 해.",
        },
    )
