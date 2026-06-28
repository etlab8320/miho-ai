"""Sports performance report templates and prescription contracts."""

from __future__ import annotations

import json
from typing import Any, Callable

from .catalog import normalize_exercise
from .local_references import LOCAL_REF_PREFIX
from .training_programs import training_program_for

TemplateBuilder = Callable[[], dict[str, Any]]


def report_template_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = build_report_template_response(args or {})
    return json.dumps(payload, ensure_ascii=False)


def build_report_template_response(args: dict[str, Any]) -> dict[str, Any]:
    exercise = normalize_exercise(args.get("exercise") or "standing_long_jump")
    if exercise is None:
        return _unsupported()
    builder = _TEMPLATE_BUILDERS.get(exercise["key"])
    if builder is None:
        return _unsupported()
    return {"ok": True, "schema_version": 1, "exercise": exercise, "template": builder()}


def _unsupported() -> dict[str, Any]:
    return {"ok": False, "errors": ["현재 변인/처방/PDF 템플릿은 제멀, 왕복달리기, 메디신볼부터 지원한다."]}


def standing_long_jump_report_template() -> dict[str, Any]:
    return _template(
        exercise_key="standing_long_jump",
        template_key="standing_long_jump_v1",
        variable_groups=_slj_variable_groups(),
        reference_groups=_SLJ_REFERENCE_GROUPS,
        prescriptions=[
            _rx("takeoff_result", "이륙각도나 수직속도가 낮고 수평속도만 높은 경우",
                ["포즈 브로드점프 4x3", "낮은 강도 수직-수평 전환 점프 4x4", "이륙각 영상 피드백 6회"],
                "앞으로만 미는 느낌에서, 마지막 순간 지면을 사선 위로 밀게 한다.",
                ["optimum_takeoff_angle", "biomechanics"]),
            _rx("horizontal_velocity_loss", "이륙각도는 좋아졌지만 수평속도가 크게 떨어진 경우",
                ["짧은 반동 브로드점프 5x3", "수평 푸시 스틱 랜딩 4x4", "팔스윙 제한-허용 비교 점프 3세트"],
                "위로 띄우되 앞으로 나가는 속도를 버리지 않게 한다.",
                ["biomechanics", "arm_swing"]),
            _rx("transition_speed", "무게중심 하강은 충분한데 도약 전환시간이 긴 경우",
                ["빠른 반전 CMJ 5x3", "메트로놈 카운터무브먼트 4x4", "깊이 제한 브로드점프 4x4"],
                "더 깊게가 아니라 내려가자마자 바로 튀어나오게 한다.",
                ["countermovement"]),
            _rx("hip_drive", "고관절 각속도나 고관절 이륙각이 상위권 대비 약한 경우",
                ["힙힌지 브로드점프 4x4", "케틀벨 스윙 패턴 4x8", "엉덩이 밀기 포커스 점프 4x3"],
                "무릎으로 먼저 펴지 말고 엉덩이로 지면을 밀어낸다.",
                ["biomechanics"]),
            _rx("arm_swing", "팔 백스윙 또는 전방 스윙 속도가 낮은 경우",
                ["암스윙 브로드점프 5x3", "백스윙 정지 후 점프 4x3", "팔스윙 타이밍 영상 피드백"],
                "팔은 장식이 아니라 몸통과 하체 추진을 앞쪽으로 연결하는 장치다.",
                ["arm_swing"]),
            _rx("landing_efficiency", "공중 다리 당김이나 착지 무게중심-발 거리가 낮은 경우",
                ["스틱 랜딩 4x4", "니터크 착지 연습 4x5", "발 앞으로 두고 엉덩이 뒤로 받기 4x4"],
                "멀리 뻗되 착지 후 뒤로 손이 짚히지 않게 한다.",
                ["landing"]),
        ],
    )


def shuttle_run_report_template() -> dict[str, Any]:
    return _template(
        exercise_key="shuttle_run",
        template_key="shuttle_run_v1",
        variable_groups=[
            _group("change_of_direction", "방향전환 결정 변인", 1, [
                _var("contact_time", "접지시간", "방향전환 발이 지면에 머무는 시간이다.",
                     "lower_is_better", ["contact_time"], "change_of_direction"),
                _var("turn_angle", "방향전환각", "몸을 꺾는 각도와 방향전환 라인이다.",
                     "range_is_better", ["turn_angle"], "change_of_direction"),
                _var("deceleration_distance", "감속거리", "속도를 줄이는 데 필요한 거리다.",
                     "lower_with_control_is_better", ["deceleration_control"], "deceleration"),
                _var("trunk_lean", "상체기울기", "중심을 낮추고 재가속 방향을 만드는 자세다.",
                     "range_is_better", ["trunk_lean"], "sprint_mechanics"),
            ], "짧고 안정적인 접지, 과하지 않은 감속, 낮은 중심 전환을 우선한다."),
            _group("reacceleration", "재가속 보조 변인", 2, [
                _var("first_step_projection", "전환 후 첫걸음 투사", "전환 뒤 첫 스텝이 진행 방향으로 나가는 정도다.",
                     "higher_is_better", ["reacceleration"], "sprint_mechanics"),
                _var("foot_contact_timing", "발 접촉 타이밍", "발 접지와 이지 시점의 빠른 전환이다.",
                     "faster_is_better", ["contact_time"], "foot_contact"),
            ], "전환 직후 첫걸음이 늦으면 기록 손실이 커진다."),
        ],
        reference_groups=_SHUTTLE_REFERENCE_GROUPS,
        prescriptions=[
            _rx("contact_time", "접지시간이 전국 성별 상위 1% 모델보다 긴 경우",
                ["낮은 중심 컷 스텝 5x4", "5-10-5 짧은 접지 드릴 4세트", "한 발 스틱-리바운드 4x4"],
                "발을 오래 누르지 말고 짧게 잡고 바로 밀어낸다.",
                ["change_of_direction", "foot_contact"]),
            _rx("deceleration_control", "감속거리가 길거나 중심이 뒤에 남는 경우",
                ["감속-스틱 4x3", "2스텝 감속 후 재가속 5x3", "낮은 중심 브레이크 드릴 4x4"],
                "멀리서 멈추지 말고 짧게 감속해 다음 방향으로 몸을 세팅한다.",
                ["deceleration"]),
            _rx("trunk_lean", "상체기울기가 너무 서거나 과하게 무너지는 경우",
                ["사이드 런지 컷 4x5", "거울 피드백 방향전환 5회", "메디신볼 안고 컷 스텝 4x4"],
                "상체를 낮추되 허리가 접히지 않고 중심이 발 안쪽에 머물게 한다.",
                ["sprint_mechanics"]),
            _rx("reacceleration", "전환 후 첫걸음이 늦거나 진행 방향으로 못 나가는 경우",
                ["전환 후 3보 가속 6회", "밴드 저항 재가속 4x5", "코너 탈출 스타트 5x3"],
                "돌자마자 첫걸음이 기록을 다시 만든다는 기준으로 훈련한다.",
                ["sprint_mechanics"]),
        ],
    )


def medicine_ball_throw_report_template() -> dict[str, Any]:
    return _template(
        exercise_key="medicine_ball_throw",
        template_key="medicine_ball_throw_v1",
        variable_groups=[
            _group("release_quality", "릴리즈 결정 변인", 1, [
                _var("release_angle", "릴리즈각", "공을 놓는 순간의 투사 각도다.",
                     "range_is_better", ["release_angle"], "release_angle"),
                _var("release_height", "릴리즈높이", "공을 놓는 높이다.",
                     "higher_is_better", ["release_height"], "medicine_ball_power"),
            ], "각도와 높이가 함께 맞아야 같은 힘도 거리로 전환된다."),
            _group("kinetic_chain", "하체-몸통-팔 연결 변인", 2, [
                _var("trunk_rotation", "몸통회전", "몸통 회전이 공으로 전달되는 정도다.",
                     "higher_is_better", ["trunk_rotation"], "medicine_ball_power"),
                _var("hip_extension", "고관절신전", "하체와 고관절이 던지기에 기여하는 정도다.",
                     "higher_is_better", ["hip_drive"], "medicine_ball_power"),
                _var("sequence_timing", "분절 타이밍", "하체-몸통-팔이 이어지는 순서다.",
                     "sequence_is_better", ["sequence_timing"], "medicine_ball_power"),
            ], "팔 힘만 쓰면 초기 속도와 릴리즈 안정성이 같이 떨어진다."),
        ],
        reference_groups=_MEDICINE_REFERENCE_GROUPS,
        prescriptions=[
            _rx("release_angle", "릴리즈각이 전국 성별 상위 1% 모델 범위에서 벗어난 경우",
                ["월 타깃 릴리즈 5x5", "무릎앉아 각도 고정 토스 4x5", "릴리즈 프리즈 영상 피드백"],
                "높이만 띄우거나 앞으로만 밀지 말고 목표 각도 안에서 놓게 한다.",
                ["release_angle"]),
            _rx("release_height", "릴리즈높이가 낮아 투사 거리가 손실되는 경우",
                ["오버헤드 익스텐션 토스 4x5", "키 큰 자세 릴리즈 드릴 4x4", "스텝-리치 토스 4x5"],
                "몸이 접힌 상태에서 던지지 말고 길게 뻗은 위치에서 놓는다.",
                ["medicine_ball_power"]),
            _rx("trunk_rotation", "몸통회전 기여가 낮고 팔 위주로 던지는 경우",
                ["스쿱 토스 5x4", "힙-트렁크 분리 회전 드릴 4x5", "측면 메디신볼 로테이션 4x6"],
                "팔보다 먼저 골반과 몸통이 공을 끌고 나오게 한다.",
                ["medicine_ball_power"]),
            _rx("hip_drive", "고관절신전이 약해 하체 힘이 공으로 안 넘어가는 경우",
                ["힙 드라이브 토스 5x4", "박스 스쿼트-토스 4x5", "브로드점프 후 토스 연결 4x3"],
                "무릎만 펴지 말고 엉덩이로 바닥을 밀어 던진다.",
                ["medicine_ball_power"]),
            _rx("sequence_timing", "하체-몸통-팔 타이밍이 동시에 무너지는 경우",
                ["스텝-릴리즈 리듬 5x4", "분절 정지 후 연속 토스 4x4", "느린 동작-빠른 릴리즈 대비"],
                "하체, 몸통, 팔이 한꺼번에 나가지 않고 순서대로 이어지게 한다.",
                ["medicine_ball_power"]),
        ],
    )


def _template(
    *,
    exercise_key: str,
    template_key: str,
    variable_groups: list[dict[str, Any]],
    reference_groups: dict[str, list[dict[str, str]]],
    prescriptions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "template_key": template_key,
        "source_policy": {
            "primary_data": "max_analysis_variables_api_or_vendor_motion_api",
            "cohort_data": "weekly_sqlite_national_gender_snapshot",
            "primary_evidence": "sports_local_reference",
            "fallback_evidence": "pe_brain",
        },
        "comparison_layers": [
            "student_latest_vs_student_previous",
            "student_latest_vs_national_gender_elite_1pct",
            "student_latest_vs_national_gender_elite_5pct",
        ],
        "variable_groups": variable_groups,
        "reference_groups": reference_groups,
        "prescription_library": prescriptions,
        "training_program": training_program_for(exercise_key),
        "pdf_contract": _pdf_contract(),
        "llm_validation_contract": _llm_validation_contract(),
        "review_contract": _review_contract(),
    }


def _group(key: str, title: str, priority: int, variables: list[dict[str, Any]], interpretation: str) -> dict[str, Any]:
    return {"group_key": key, "title": title, "priority": priority, "variables": variables, "interpretation": interpretation}


def _var(
    key: str,
    name: str,
    role: str,
    direction: str,
    prescription_targets: list[str],
    reference_group: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "role": role,
        "direction": direction,
        "comparison_basis": "national_gender_elite_distribution",
        "prescription_targets": prescription_targets,
        "reference_group": reference_group,
    }


def _rx(target: str, when: str, drills: list[str], coaching_cue: str, evidence_groups: list[str]) -> dict[str, Any]:
    return {
        "target": target,
        "when": when,
        "drills": drills,
        "coaching_cue": coaching_cue,
        "evidence_groups": evidence_groups,
    }


def _pdf_contract() -> list[dict[str, str]]:
    return [
        {"section": "cover", "title": "학생/성별/측정일/종목/기록"},
        {"section": "record_trend", "title": "최근 기록과 이전 기록 변화"},
        {"section": "cohort_position", "title": "전국 성별 상위 1%·5% 모델 비교"},
        {"section": "variable_scorecard", "title": "핵심 변인 점수표"},
        {"section": "bottleneck_analysis", "title": "우선 개선점 3개"},
        {"section": "prescription", "title": "2주 운동처방"},
        {"section": "evidence", "title": "적용 변인과 레퍼런스"},
        {"section": "review", "title": "코치/리뷰어 검증 메모"},
    ]


def _llm_validation_contract() -> dict[str, Any]:
    return {
        "requires_variable_direction": True,
        "requires_evidence_link": True,
        "requires_prescription_target": True,
        "requires_training_dosage": True,
        "requires_multi_variable_effect_map": True,
        "allowed_basis": [
            "student_latest_vs_student_previous",
            "student_latest_vs_national_gender_elite_1pct",
            "student_latest_vs_national_gender_elite_5pct",
        ],
        "reject_if": [
            "변인 방향과 반대로 처방을 권한다.",
            "근거 그룹 없는 운동을 핵심 처방으로 확정한다.",
            "지점별 상위권을 최종 모델로 사용한다.",
            "통증 또는 부상 판단을 의료 진단처럼 쓴다.",
        ],
    }


def _review_contract() -> dict[str, list[str]]:
    return {
        "must_have": [
            "최신 기록과 이전 기록을 분리한다.",
            "전국 성별 상위 1%·5% 모델 대비를 사용한다.",
            "각 부족점은 최소 1개 이상 변인, 처방, 근거 그룹에 연결한다.",
            "근거는 sports_ref 또는 accepted evidence pack으로 표시한다.",
        ],
        "must_not_have": [
            "상위권 학생에게 부족하다고만 단정하지 않는다.",
            "지점별 상위권을 전국 모델처럼 쓰지 않는다.",
            "근거 없는 최적 각도나 절대 기준을 확정값처럼 쓰지 않는다.",
        ],
    }


def _slj_variable_groups() -> list[dict[str, Any]]:
    return [
        _group("takeoff_result", "기록 결정 변인", 1, [
            _var("takeoff_angle", "이륙각도", "도약 순간 속도 방향을 보여준다.",
                 "range_is_better", ["takeoff_result"], "optimum_takeoff_angle"),
            _var("horizontal_velocity", "수평속도", "앞으로 밀고 나가는 속도다.",
                 "higher_is_better", ["horizontal_velocity_loss"], "biomechanics"),
            _var("vertical_velocity", "수직속도", "체공 성분과 이륙각 형성에 관여한다.",
                 "higher_with_horizontal_balance", ["takeoff_result"], "optimum_takeoff_angle"),
            _var("takeoff_transition_time", "도약 전환시간", "앉은 뒤 밀고 나가기까지 걸린 시간이다.",
                 "lower_is_better", ["transition_speed"], "countermovement"),
        ], "기록은 수평속도, 수직속도, 이륙각도, 전환시간의 균형으로 판단한다."),
        _group("propulsion_chain", "하체 추진 변인", 2, [
            _var("hip_peak_angular_velocity", "엉덩관절 최대각속도", "고관절 신전 추진 타이밍이다.",
                 "higher_is_better", ["hip_drive"], "biomechanics"),
            _var("knee_peak_angular_velocity", "무릎관절 최대각속도", "무릎 신전 출력 흐름이다.",
                 "higher_is_better", ["hip_drive"], "biomechanics"),
            _var("ankle_peak_angular_velocity", "발목관절 최대각속도", "마지막 발목 스냅 출력이다.",
                 "higher_is_better", ["takeoff_result"], "ankle_mobility"),
            _var("hip_takeoff_angle", "엉덩관절 이륙각도", "이륙 순간 고관절 신전 완성도다.",
                 "range_is_better", ["hip_drive"], "biomechanics"),
            _var("knee_takeoff_angle", "무릎관절 이륙각도", "이륙 순간 무릎 신전 완성도다.",
                 "range_is_better", ["hip_drive"], "biomechanics"),
            _var("ankle_takeoff_angle", "발목관절 이륙각도", "이륙 순간 발목 신전 완성도다.",
                 "range_is_better", ["takeoff_result"], "ankle_mobility"),
        ], "고관절-무릎-발목 순서가 끊기면 속도는 있어도 거리로 전환되지 않는다."),
        _group("countermovement_arm", "반동·팔스윙 변인", 3, [
            _var("arm_backswing_angle", "팔 백스윙 각도", "도약 전 팔 반동 준비 크기다.",
                 "range_is_better", ["arm_swing"], "arm_swing"),
            _var("arm_swing_peak_velocity", "팔 전방 스윙 속도", "전방 팔스윙 기여도다.",
                 "higher_is_better", ["arm_swing"], "arm_swing"),
            _var("com_descent_distance", "무게중심 하강량", "반동 준비 깊이다.",
                 "range_is_better", ["transition_speed"], "countermovement"),
            _var("descent_velocity", "하강속도 최대", "반동 진입 속도다.",
                 "faster_is_better", ["transition_speed"], "countermovement"),
        ], "깊게 앉는 것보다 빠르게 반전해 추진으로 연결되는지가 중요하다."),
        _group("landing_efficiency", "착지·유효거리 변인", 4, [
            _var("com_foot_distance", "착지 무게중심-발 거리", "착지 시 발을 얼마나 앞에 둘 수 있는지다.",
                 "higher_with_control", ["landing_efficiency"], "landing"),
            _var("flight_hip_min_angle", "비행구간 엉덩관절 최소각도", "공중에서 다리를 당기는 정도다.",
                 "range_is_better", ["landing_efficiency"], "landing"),
            _var("flight_knee_min_angle", "비행구간 무릎관절 최소각도", "착지 준비를 위한 무릎 접힘 정도다.",
                 "range_is_better", ["landing_efficiency"], "landing"),
        ], "착지는 기록을 늘리지만 과도하면 뒤로 넘어가거나 무릎 부담이 커질 수 있다."),
    ]


def _ref(ref_id: str, title: str) -> dict[str, str]:
    return {"ref": f"{LOCAL_REF_PREFIX}{ref_id}", "title": title, "source": "sports_local_reference"}


_SLJ_REFERENCE_GROUPS = {
    "optimum_takeoff_angle": [_ref("48b9ec94918cb284", "Optimum Take-off Angle in the Standing Long Jump")],
    "biomechanics": [
        _ref("d3a636a70382d5cb", "Biomechanical Analysis of the Standing Long Jump"),
        _ref("dfc89a3877dce127", "제자리멀리뛰기 기록과 운동역학적 요인들의 상관관계 연구"),
    ],
    "arm_swing": [
        _ref("4ca94bd6af801405", "Role of Arm Motion in the Standing Long Jump"),
        _ref("9870c80dcc9e11fe", "Optimal Control Simulations Reveal Mechanisms by Which Arm Movement Improves Standing Long Jump Performance"),
    ],
    "countermovement": [
        _ref("38911e8f4fd3256d", "Larger Countermovement Increases the Jump Height of Countermovement Jump"),
        _ref("f6f961d5ff326fea", "Relationships Between Countermovement Jump Ground Reaction Forces and Jump Height, Reactive Strength Index, and Jump Time"),
    ],
    "ankle_mobility": [_ref("50cc1342a8307bf6", "Relationship between Ankle Dorsiflexion Range of Motion and Sprinting and Jumping Ability in Young Athletes")],
    "landing": [_ref("58ceb92e1a3eb4e6", "How to Improve the Standing Long Jump Performance A Mininarrative Review")],
}

_SHUTTLE_REFERENCE_GROUPS = {
    "change_of_direction": [_ref("9cd450fdd4a93839", "Mechanical Determinants of Faster Change of Direction Speed Performance in Male Athletes")],
    "deceleration": [_ref("9f3956b74958c910", "Biomechanical and Neuromuscular Performance Requirements of Horizontal Deceleration")],
    "sprint_mechanics": [
        _ref("5db5209785f59dee", "Biomechanics of Sprint Running - A Review"),
        _ref("5e1212165764c035", "Determinant Biomechanical Variables for Each Sprint Phase Performance"),
    ],
    "foot_contact": [_ref("1cfe87e5d410be43", "Automatic high fidelity foot contact location and timing for elite sprinting")],
}

_MEDICINE_REFERENCE_GROUPS = {
    "release_angle": [_ref("bac12efefeb65b57", "Optimum release angle in the shot put")],
    "medicine_ball_power": [
        _ref("ba7742bb78cf8260", "Validity and Reliability of a Medicine Ball Explosive Power Test"),
        _ref("69aefae9c00aca02", "The Effect of Two-Handed Overhead Medicine Ball Throwing Exercises"),
        _ref("268c4a132e9cd8ff", "Model Calculation of the Influence of Body Height on Performance in Medicine Ball Throw"),
    ],
}

_TEMPLATE_BUILDERS: dict[str, TemplateBuilder] = {
    "standing_long_jump": standing_long_jump_report_template,
    "shuttle_run": shuttle_run_report_template,
    "medicine_ball_throw": medicine_ball_throw_report_template,
}
