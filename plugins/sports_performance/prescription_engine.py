"""Student-specific variable gap and prescription selection."""

from __future__ import annotations

import re
from typing import Any, Callable

from .exercise_library import select_exercise_library_blocks
from .variable_compare import comparison_pair

TargetLabeler = Callable[[Any], str]

_HIGHER_DIRECTIONS = {
    "higher_is_better",
    "faster_is_better",
    "higher_with_horizontal_balance",
    "higher_with_control",
}
_LOWER_DIRECTIONS = {"lower_is_better", "lower_with_control_is_better"}
_RANGE_DIRECTIONS = {"range_is_better"}
_VALUE_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")

_STRENGTH_LIBRARY: dict[str, dict[str, Any]] = {
    "horizontal_velocity_loss": {
        "title": "스플릿 스쿼트와 수평 푸시 보강",
        "why": "앞으로 미는 속도가 낮을 때 한쪽 다리로 지면을 뒤로 미는 힘을 키운다.",
        "student_steps": ["한 발을 앞으로 둔다.", "앞발로 바닥을 뒤로 민다.", "몸이 위로만 뜨지 않게 앞으로 밀어낸다."],
        "coach_cue": "앞발로 바닥을 뒤로 밀어.",
        "sets": "4",
        "reps_or_time": "6회/측",
        "load": "자세가 흔들리지 않는 낮은 부하",
        "evidence_groups": ["biomechanics"],
    },
    "takeoff_result": {
        "title": "발목-무릎 빠른 신전 점프 스쿼트",
        "why": "발목 각도, 발목 각속도, 무릎 신전 속도가 낮을 때 짧은 시간에 펴는 힘을 보강한다.",
        "student_steps": ["가벼운 덤벨을 들거나 맨몸으로 선다.", "조금만 앉았다가 빠르게 편다.", "착지 후 바로 자세를 멈춘다."],
        "coach_cue": "깊게 앉지 말고 발목과 무릎을 빠르게 펴.",
        "sets": "4",
        "reps_or_time": "3회",
        "load": "체중 또는 가벼운 부하",
        "evidence_groups": ["optimum_takeoff_angle", "biomechanics"],
    },
    "transition_speed": {
        "title": "반동 빠른 점프 스쿼트",
        "why": "앉은 뒤 멈추는 시간을 줄이고 바로 밀고 나오는 전환 속도를 키운다.",
        "student_steps": ["작게 앉는다.", "멈추지 말고 바로 뛴다.", "착지 후 2초 동안 흔들리지 않는다."],
        "coach_cue": "앉자마자 바로 나와.",
        "sets": "5",
        "reps_or_time": "3회",
        "load": "속도가 유지되는 가벼운 부하",
        "evidence_groups": ["countermovement"],
    },
    "hip_drive": {
        "title": "루마니안 데드리프트와 힙쓰러스트",
        "why": "엉덩이와 허벅지 뒤쪽 힘이 약할 때 고관절 신전 출력을 보강한다.",
        "student_steps": ["엉덩이를 뒤로 접는다.", "허리를 꺾지 않고 엉덩이에 힘을 준다.", "올라올 때 엉덩이를 끝까지 편다."],
        "coach_cue": "허리 말고 엉덩이로 펴.",
        "sets": "4",
        "reps_or_time": "6-8회",
        "load": "허리 보상 없는 낮은 부하",
        "evidence_groups": ["biomechanics"],
    },
    "arm_swing": {
        "title": "메디신볼 스윙 리듬 보강",
        "why": "팔스윙이 하체 추진과 맞지 않을 때 몸통-팔 연결 타이밍을 만든다.",
        "student_steps": ["가벼운 볼을 가슴 앞에 든다.", "팔과 엉덩이를 같이 뒤로 보낸다.", "다리 펴는 순간 볼을 앞으로 보낸다."],
        "coach_cue": "팔만 던지지 말고 다리랑 같이 보내.",
        "sets": "4",
        "reps_or_time": "5회",
        "load": "가벼운 메디신볼",
        "evidence_groups": ["arm_swing"],
    },
    "landing_efficiency": {
        "title": "착지 감속 스플릿 스쿼트와 수건 햄스트링 컬",
        "why": "착지 때 발을 앞으로 뻗고도 뒤로 넘어가지 않도록 감속 제어를 키운다.",
        "student_steps": ["스플릿 스쿼트는 3초 동안 천천히 내려간다.", "수건 컬은 누워서 발뒤꿈치를 천천히 멀리 보낸다.", "착지 연습 때 발을 앞으로 뻗고 무릎을 접는다."],
        "coach_cue": "멀리 뻗고도 뒤로 넘어가지 않게 버텨.",
        "sets": "3",
        "reps_or_time": "6회/측",
        "load": "체중, 수건 또는 슬라이더",
        "evidence_groups": ["landing"],
    },
    "contact_time": {
        "title": "짧은 접지 포고 점프",
        "why": "방향전환 때 발이 오래 머무는 학생의 빠른 접지 반응을 만든다.",
        "sets": "4",
        "reps_or_time": "8초",
        "load": "체중",
        "evidence_groups": ["change_of_direction", "foot_contact"],
    },
    "deceleration_control": {
        "title": "감속 런지와 스틱 착지",
        "why": "짧게 멈추고 다시 뛰기 위한 하체 제동력을 만든다.",
        "sets": "4",
        "reps_or_time": "5회/측",
        "load": "체중 또는 가벼운 덤벨",
        "evidence_groups": ["deceleration"],
    },
    "trunk_rotation": {
        "title": "회전 메디신볼 던지기",
        "why": "몸통 회전이 공으로 전달되지 않을 때 골반-몸통 연결을 훈련한다.",
        "sets": "4",
        "reps_or_time": "6회",
        "load": "가벼운 메디신볼",
        "evidence_groups": ["medicine_ball_power"],
    },
    "sequence_timing": {
        "title": "분절 정지 후 연속 던지기",
        "why": "하체, 몸통, 팔이 동시에 무너지는 학생의 순서를 다시 만든다.",
        "sets": "4",
        "reps_or_time": "4회",
        "load": "실전보다 가벼운 공",
        "evidence_groups": ["medicine_ball_power"],
    },
}


def build_personalized_prescription(
    *,
    variable_groups: list[dict[str, Any]],
    training_program: dict[str, Any],
    target_labeler: TargetLabeler | None = None,
) -> dict[str, Any]:
    labeler = target_labeler or (lambda value: str(value or "").replace("_", " "))
    analyzed_groups = [_analyzed_group(group) for group in variable_groups]
    variables = _variable_index(analyzed_groups)
    target_scores = _target_scores(variables)
    return {
        "variable_groups": analyzed_groups,
        "strengths": _strengths(variables, labeler),
        "bottlenecks": _bottlenecks(variables, labeler),
        "training_program": _training_program(training_program, variables, target_scores),
        "target_scores": target_scores,
    }


def _analyzed_group(group: dict[str, Any]) -> dict[str, Any]:
    return {
        **group,
        "variables": [_analyzed_variable(variable) for variable in group.get("variables") or []],
    }


def _analyzed_variable(variable: dict[str, Any]) -> dict[str, Any]:
    current, unit = _parse_measure(variable.get("current"))
    elite, elite_unit = _parse_measure(variable.get("elite_1pct"))
    if current is None or elite is None:
        return {**variable, "deficit_score": 0.0, "advantage_score": 0.0, "diagnosis": _missing_model_diagnosis(variable)}
    unit = unit or elite_unit
    current_cmp, elite_cmp = comparison_pair(str(variable.get("key") or ""), current, elite)
    if current_cmp is None or elite_cmp is None:
        return {**variable, "deficit_score": 0.0, "advantage_score": 0.0, "diagnosis": _missing_model_diagnosis(variable)}
    diff = current_cmp - elite_cmp
    direction = str(variable.get("direction") or "")
    deficit_score = _deficit_score(direction, current_cmp, elite_cmp)
    advantage_score = _advantage_score(direction, current_cmp, elite_cmp)
    status = _status(direction, diff, unit)
    return {
        **variable,
        "gap": _format_gap(diff, unit),
        "status": status,
        "deficit_score": round(deficit_score, 4),
        "advantage_score": round(advantage_score, 4),
        "diagnosis": _diagnosis(variable, status),
    }


def _variable_index(groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(variable.get("key")): variable
        for group in groups
        for variable in group.get("variables") or []
        if str(variable.get("key") or "")
    }


def _target_scores(variables: dict[str, dict[str, Any]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for variable in variables.values():
        score = float(variable.get("deficit_score") or 0.0)
        if score <= 0:
            continue
        for target in variable.get("prescription_targets") or []:
            key = str(target or "")
            scores[key] = scores.get(key, 0.0) + score
    return scores


def _training_program(
    program: dict[str, Any],
    variables: dict[str, dict[str, Any]],
    target_scores: dict[str, float],
) -> dict[str, Any]:
    blocks = _ranked_blocks(program.get("exercise_blocks") or [], variables, target_scores)
    library_blocks = select_exercise_library_blocks(
        exercise_key=str(program.get("program_key") or ""),
        variables=variables,
        target_scores=target_scores,
    )
    strength_blocks = _strength_blocks(target_scores, variables, library_blocks)
    objective = _objective(program.get("objective"), blocks, strength_blocks)
    return {
        **program,
        "objective": objective,
        "exercise_blocks": blocks,
        "strength_blocks": strength_blocks,
        "exercise_library_blocks": library_blocks,
    }


def _ranked_blocks(
    raw_blocks: list[dict[str, Any]],
    variables: dict[str, dict[str, Any]],
    target_scores: dict[str, float],
) -> list[dict[str, Any]]:
    scored = [(_block_score(block, variables, target_scores), block) for block in raw_blocks]
    if not any(score > 0 for score, _ in scored):
        return [_with_reason(block, variables, score=0.0) for _, block in scored]
    ranked = sorted(scored, key=lambda item: item[0], reverse=True)[:3]
    return [_with_reason(block, variables, score=score) for score, block in ranked]


def _block_score(block: dict[str, Any], variables: dict[str, dict[str, Any]], target_scores: dict[str, float]) -> float:
    score = target_scores.get(str(block.get("prescription_target") or ""), 0.0) * 2.0
    score += _variables_score(block.get("primary_variables"), variables, weight=1.4)
    score += _variables_score(block.get("secondary_variables"), variables, weight=0.7)
    return score


def _variables_score(keys: Any, variables: dict[str, dict[str, Any]], *, weight: float) -> float:
    if not isinstance(keys, list):
        return 0.0
    return sum(float(variables.get(str(key), {}).get("deficit_score") or 0.0) * weight for key in keys)


def _with_reason(block: dict[str, Any], variables: dict[str, dict[str, Any]], *, score: float) -> dict[str, Any]:
    relevant = _relevant_variables(block, variables)
    return {
        **block,
        "selection_score": round(score, 4),
        "student_reason": _student_reason(relevant),
        "variable_effect_notes": [_effect_note(variable) for variable in relevant[:4]],
    }


def _relevant_variables(block: dict[str, Any], variables: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    keys = [*(block.get("primary_variables") or []), *(block.get("secondary_variables") or [])]
    rows = [variables[str(key)] for key in keys if str(key) in variables]
    rows.sort(key=lambda variable: float(variable.get("deficit_score") or 0.0), reverse=True)
    return rows


def _student_reason(variables: list[dict[str, Any]]) -> str:
    deficits = [variable for variable in variables if float(variable.get("deficit_score") or 0.0) > 0]
    source = deficits or variables[:2]
    if not source:
        return "측정 변인 연결 후 개인별 우선순위를 확정한다."
    return _reason_part(source[0])


def _reason_part(variable: dict[str, Any]) -> str:
    return (
        f"{variable.get('display_name')}: 현재 {variable.get('current')} vs 상위 1% "
        f"{variable.get('elite_1pct')}, 차이 {variable.get('gap')}. {variable.get('diagnosis')}"
    )


def _effect_note(variable: dict[str, Any]) -> str:
    return f"{variable.get('display_name')}: {variable.get('diagnosis')}"


def _strength_blocks(
    target_scores: dict[str, float],
    variables: dict[str, dict[str, Any]],
    library_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered_targets = [key for key, _ in sorted(target_scores.items(), key=lambda item: item[1], reverse=True)]
    covered_targets = {str(block.get("target") or "") for block in library_blocks[:3]}
    blocks: list[dict[str, Any]] = []
    for target in ordered_targets:
        if target in covered_targets:
            continue
        template = _STRENGTH_LIBRARY.get(target)
        if not template:
            continue
        blocks.append({**template, "target": target, "student_reason": _target_reason(target, variables)})
        if len(blocks) == 2:
            break
    return blocks or [_point_focus_block()]


def _target_reason(target: str, variables: dict[str, dict[str, Any]]) -> str:
    linked = [
        variable
        for variable in variables.values()
        if target in (variable.get("prescription_targets") or []) and float(variable.get("deficit_score") or 0.0) > 0
    ]
    linked.sort(key=lambda variable: float(variable.get("deficit_score") or 0.0), reverse=True)
    return _student_reason(linked)


def _point_focus_block() -> dict[str, Any]:
    return {
        "target": "point_focus",
        "title": "메인 3개 포인트 처방 집중",
        "why": "핵심 결손이 이미 메인 처방에 들어갔으므로 운동을 더 늘리지 않고 품질을 고정한다.",
        "sets": "3",
        "reps_or_time": "메인 처방 품질 확인",
        "load": "추가 부하 없음",
        "evidence_groups": ["biomechanics"],
        "student_steps": ["메인 3개 운동만 먼저 수행한다.", "각 세트 후 영상으로 목표 변인을 확인한다.", "품질이 무너지면 운동 수를 늘리지 않는다."],
        "coach_cue": "오늘은 더 많이가 아니라 목표 변인만 정확히.",
        "student_reason": "메인 처방이 핵심 결손 타깃을 이미 커버해 중복 운동을 제외했다.",
    }


def _bottlenecks(variables: dict[str, dict[str, Any]], labeler: TargetLabeler) -> list[dict[str, str]]:
    rows = sorted(variables.values(), key=lambda variable: float(variable.get("deficit_score") or 0.0), reverse=True)
    selected = [row for row in rows if float(row.get("deficit_score") or 0.0) > 0][:3] or rows[:3]
    return [
        {
            "title": str(variable.get("display_name") or variable.get("key") or ""),
            "target": ", ".join(labeler(target) for target in variable.get("prescription_targets") or []),
            "why": str(variable.get("diagnosis") or variable.get("display_role") or ""),
            "direction": str(variable.get("status") or variable.get("direction_label") or ""),
            "current": str(variable.get("current") or ""),
            "elite_1pct": str(variable.get("elite_1pct") or ""),
            "gap": str(variable.get("gap") or ""),
        }
        for variable in selected
    ]


def _strengths(variables: dict[str, dict[str, Any]], labeler: TargetLabeler) -> list[dict[str, str]]:
    rows = sorted(variables.values(), key=lambda variable: float(variable.get("advantage_score") or 0.0), reverse=True)
    selected = [row for row in rows if float(row.get("advantage_score") or 0.0) > 0][:3]
    if not selected:
        selected = [row for row in rows if float(row.get("deficit_score") or 0.0) <= 0][:3]
    return [
        {
            "title": str(variable.get("display_name") or variable.get("key") or ""),
            "target": ", ".join(labeler(target) for target in variable.get("prescription_targets") or []),
            "why": _strength_reason(variable),
            "status": str(variable.get("status") or variable.get("direction_label") or ""),
            "current": str(variable.get("current") or ""),
            "elite_1pct": str(variable.get("elite_1pct") or ""),
            "gap": str(variable.get("gap") or ""),
        }
        for variable in selected
    ]


def _objective(raw: Any, blocks: list[dict[str, Any]], strength_blocks: list[dict[str, Any]]) -> str:
    if not blocks or not strength_blocks:
        return str(raw or "")
    return f"{blocks[0]['title']}와 {strength_blocks[0]['title']}를 우선해 개인별 결손 변인을 보강한다."


def _parse_measure(value: Any) -> tuple[float | None, str]:
    text = str(value or "").strip()
    match = _VALUE_PATTERN.search(text)
    if not match:
        return None, ""
    unit = text[match.end():].strip()
    try:
        return float(match.group()), unit
    except ValueError:
        return None, unit


def _deficit_score(direction: str, current: float, elite: float) -> float:
    tolerance = _tolerance(elite)
    if direction in _LOWER_DIRECTIONS:
        return max(0.0, current - elite - tolerance) / max(abs(elite), 0.01)
    if direction in _RANGE_DIRECTIONS:
        return max(0.0, abs(current - elite) - tolerance) / max(abs(elite), 0.01)
    if direction in _HIGHER_DIRECTIONS:
        return max(0.0, elite - current - tolerance) / max(abs(elite), 0.01)
    return 0.0


def _advantage_score(direction: str, current: float, elite: float) -> float:
    tolerance = _tolerance(elite)
    if direction in _LOWER_DIRECTIONS:
        return max(0.0, elite - current - tolerance) / max(abs(elite), 0.01)
    if direction in _HIGHER_DIRECTIONS:
        return max(0.0, current - elite - tolerance) / max(abs(elite), 0.01)
    return 0.0


def _status(direction: str, diff: float, unit: str) -> str:
    tolerance = _tolerance(abs(diff))
    if direction in _RANGE_DIRECTIONS:
        if diff < -tolerance:
            return "목표보다 낮음"
        if diff > tolerance:
            return "목표보다 높음"
        return "목표 범위 근접"
    if direction in _LOWER_DIRECTIONS:
        if diff > tolerance:
            return "상위 모델보다 느림" if unit == "s" else "상위 모델보다 높음"
        if diff < -tolerance:
            return "상위 모델보다 짧음" if unit == "s" else "상위 모델보다 낮음"
        return "상위 모델 근접"
    if direction in _HIGHER_DIRECTIONS and diff < -tolerance:
        return "상위 모델보다 느림" if "/s" in unit else "상위 모델보다 낮음"
    if direction in _HIGHER_DIRECTIONS and diff > tolerance:
        return "상위 모델보다 빠름" if "/s" in unit else "상위 모델보다 높음"
    return "상위 모델 근접"


def _tolerance(value: float) -> float:
    return max(abs(value) * 0.005, 0.01)


def _format_gap(diff: float, unit: str) -> str:
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.2f} {unit}".strip()


def _diagnosis(variable: dict[str, Any], status: str) -> str:
    key = str(variable.get("key") or "")
    if key == "takeoff_angle" and status == "목표보다 낮음":
        return "뛰어오르는 각도가 너무 낮게 나가 앞으로 민 힘이 거리로 덜 전환된다."
    if key == "takeoff_angle" and status == "목표보다 높음":
        return "뛰어오르는 각도가 높아 앞으로 나가는 속도를 잃을 수 있다."
    if key == "horizontal_velocity":
        return "앞으로 미는 속도가 부족해 이륙 후 거리 확보가 어렵다."
    if key == "takeoff_transition_time":
        return "앉았다 밀기까지 시간이 길어 반동이 새고 도약 시작이 늦다."
    if key == "descent_velocity":
        return "앉는 속도가 느려 반동이 추진으로 빠르게 이어지지 않는다."
    if key.startswith("hip_"):
        return "엉덩이 신전이 늦어 하체 힘이 앞으로 충분히 전달되지 않는다."
    if key.startswith("knee_"):
        return "무릎 신전 타이밍이 부족해 추진 사슬이 끊긴다."
    if key.startswith("ankle_"):
        return "마지막 발목 밀기가 약해 이륙 속도 손실이 생긴다."
    if key.startswith("arm_"):
        return "팔스윙 준비와 전방 가속이 하체 추진과 충분히 맞지 않는다."
    return f"{variable.get('display_name') or key} 변인이 상위 모델과 차이가 있어 우선 확인이 필요하다."


def _strength_reason(variable: dict[str, Any]) -> str:
    return (
        f"현재 {variable.get('current')}가 상위 1% {variable.get('elite_1pct')} 대비 "
        f"{variable.get('gap')} 수준이다."
    )


def _missing_model_diagnosis(variable: dict[str, Any]) -> str:
    return f"{variable.get('display_name') or variable.get('key')} 상위 모델 값이 없어 격차 판정을 보류한다."
