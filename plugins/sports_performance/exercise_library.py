"""Contextual exercise library for sports motion prescriptions."""

from __future__ import annotations

from typing import Any

_VERIFIED_AT = "2026-06-29"
_VERIFY_METHOD = "yt-dlp metadata + ffmpeg frame audit"
_MAX_PER_TARGET = 2
_SUPPORT_LOAD_BONUS = 0.75
_CORRECTIVE_MULTI_VARIABLE_BONUS = 0.45
_EVENT_REPETITION_PENALTY = 0.9
_CORRECTIVE_KINDS = {"static_corrective", "dynamic_corrective"}
_KIND_LABELS = {
    "static_corrective": "정적 보강",
    "dynamic_corrective": "동적 보강",
    "technical_transfer": "기술 전이",
    "event_drill": "종목 드릴",
}
_KIND_SCORE = {
    "static_corrective": 1.25,
    "dynamic_corrective": 1.05,
    "technical_transfer": 0.0,
    "event_drill": -1.2,
}
_STATIC_CORRECTIVE_KEYS = {
    "single_leg_hip_thrust",
    "romanian_deadlift",
    "wall_drive_hip_extension",
    "eccentric_split_squat",
    "towel_hamstring_curl",
    "single_leg_rdl_balance",
}
_DYNAMIC_CORRECTIVE_KEYS = {
    "fast_reversal_cmj",
    "snap_down_to_jump",
    "pogo_jump",
    "depth_drop_rebound",
    "shallow_countermovement_jump",
    "split_squat_horizontal_push",
    "kettlebell_swing_hinge",
    "standing_long_jump_arm_swing_fix",
    "jump_squat_light_load",
    "box_jump_soft_landing",
    "kneeling_jump_to_broad",
}
_EVENT_DRILL_KEYS = {
    "horizontal_push_broad_jump",
    "band_resisted_broad_jump",
    "broad_jump_stick_landing",
    "low_angle_projection_jump",
    "arm_swing_timing_jump",
    "no_arm_vs_arm_jump",
    "backswing_marker_jump",
    "takeoff_angle_marker_jump",
    "vertical_to_broad_jump",
    "stick_landing",
    "leg_reach_stick_landing",
    "medicine_ball_broad_jump",
}
_EVENT_REPETITION_TERMS = ("제멀", "멀리뛰기", "broad jump")


def select_exercise_library_blocks(
    *,
    exercise_key: str,
    variables: dict[str, dict[str, Any]],
    target_scores: dict[str, float],
    limit: int = 5,
) -> list[dict[str, Any]]:
    candidates = _EXERCISES.get(_normalize_exercise_key(exercise_key), [])
    if not candidates:
        return []

    active_keys = {
        key
        for key, variable in variables.items()
        if float(variable.get("deficit_score") or 0.0) > 0
    }
    scored = [
        (_candidate_score(item, variables, target_scores, active_keys), index, item)
        for index, item in enumerate(candidates)
    ]
    ranked = sorted(scored, key=lambda row: (row[0], -row[1]), reverse=True)
    selected: list[dict[str, Any]] = []
    target_counts: dict[str, int] = {}
    for score, _, item in ranked:
        if score <= 0 and selected:
            continue
        target = str(item.get("target") or "")
        if target_counts.get(target, 0) >= _MAX_PER_TARGET:
            continue
        selected.append(_with_student_context(item, variables, score))
        target_counts[target] = target_counts.get(target, 0) + 1
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        selected.extend(_fallback_blocks(candidates, variables, selected, limit))
    return selected[:limit]


def exercise_library_target_counts(exercise_key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in _EXERCISES.get(_normalize_exercise_key(exercise_key), []):
        target = str(item.get("target") or "")
        counts[target] = counts.get(target, 0) + 1
    return counts


def exercise_library_variable_counts(exercise_key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in _EXERCISES.get(_normalize_exercise_key(exercise_key), []):
        keys = [*(item.get("primary_variables") or []), *(item.get("secondary_variables") or [])]
        for key in keys:
            text = str(key or "")
            counts[text] = counts.get(text, 0) + 1
    return counts


def exercise_library_entries(exercise_key: str) -> list[dict[str, Any]]:
    return [dict(item) for item in _EXERCISES.get(_normalize_exercise_key(exercise_key), [])]


def _normalize_exercise_key(raw: str) -> str:
    key = str(raw or "")
    if key.startswith("standing_long_jump"):
        return "standing_long_jump"
    return key


def _candidate_score(
    item: dict[str, Any],
    variables: dict[str, dict[str, Any]],
    target_scores: dict[str, float],
    active_keys: set[str],
) -> float:
    primary = [str(key) for key in item.get("primary_variables") or []]
    secondary = [str(key) for key in item.get("secondary_variables") or []]
    covered = active_keys.intersection(primary + secondary)
    score = target_scores.get(str(item.get("target") or ""), 0.0) * 2.3
    score += _variable_score(primary, variables, 1.7)
    score += _variable_score(secondary, variables, 0.85)
    if len(covered) >= 2:
        score += 1.2 + (0.25 * len(covered))
    if active_keys.intersection(primary) and active_keys.intersection(secondary):
        score += 0.55
    kind = _exercise_kind(item)
    score += _KIND_SCORE.get(kind, 0.0)
    if kind in _CORRECTIVE_KINDS and len(covered) >= 2:
        score += _CORRECTIVE_MULTI_VARIABLE_BONUS
    score -= _event_repetition_penalty(item)
    score += _support_load_bonus(item)
    return round(score, 5)


def _variable_score(keys: list[str], variables: dict[str, dict[str, Any]], weight: float) -> float:
    return sum(float(variables.get(key, {}).get("deficit_score") or 0.0) * weight for key in keys)


def _support_load_bonus(item: dict[str, Any]) -> float:
    load = str((item.get("dosage") or {}).get("load") or "")
    if not load or load == "체중":
        return 0.0
    return _SUPPORT_LOAD_BONUS


def _exercise_kind(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "technical_transfer")
    if kind in _KIND_LABELS:
        return kind
    return "technical_transfer"


def _event_repetition_penalty(item: dict[str, Any]) -> float:
    kind = _exercise_kind(item)
    if kind == "static_corrective":
        return 0.0
    text = " ".join(
        [
            str(item.get("exercise_key") or ""),
            str(item.get("title") or ""),
            str(item.get("how_to") or ""),
        ]
    ).lower()
    if any(term.lower() in text for term in _EVENT_REPETITION_TERMS):
        return _EVENT_REPETITION_PENALTY
    return 0.0


def _with_student_context(
    item: dict[str, Any],
    variables: dict[str, dict[str, Any]],
    score: float,
) -> dict[str, Any]:
    linked = _linked_variables(item, variables)
    return {
        **item,
        "selection_score": round(score, 4),
        "linked_variables": [_variable_summary(variable) for variable in linked],
        "selection_reason": _selection_reason(linked),
        "expected_variable_changes": [_expected_change(variable) for variable in linked[:4]],
    }


def _linked_variables(item: dict[str, Any], variables: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    keys = [*(item.get("primary_variables") or []), *(item.get("secondary_variables") or [])]
    rows = [variables[str(key)] for key in keys if str(key) in variables]
    rows.sort(key=lambda row: float(row.get("deficit_score") or 0.0), reverse=True)
    return rows


def _variable_summary(variable: dict[str, Any]) -> dict[str, str]:
    return {
        "key": str(variable.get("key") or ""),
        "label": str(variable.get("display_name") or variable.get("key") or ""),
        "current": str(variable.get("current") or ""),
        "elite_1pct": str(variable.get("elite_1pct") or ""),
        "gap": str(variable.get("gap") or ""),
        "diagnosis": str(variable.get("diagnosis") or ""),
    }


def _selection_reason(variables: list[dict[str, Any]]) -> str:
    deficits = [row for row in variables if float(row.get("deficit_score") or 0.0) > 0]
    source = deficits[:2] or variables[:2]
    if not source:
        return "현재 결손 변인이 작아 기본 자세 품질 유지 운동으로 배치했다."
    parts = [
        f"{row.get('display_name')}: 현재 {row.get('current')} vs 상위 1% {row.get('elite_1pct')}, 차이 {row.get('gap')}"
        for row in source
    ]
    return " / ".join(parts)


def _expected_change(variable: dict[str, Any]) -> str:
    return f"{variable.get('display_name')}: {variable.get('diagnosis')}"


def _fallback_blocks(
    candidates: list[dict[str, Any]],
    variables: dict[str, dict[str, Any]],
    selected: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    selected_keys = {str(item.get("exercise_key") or "") for item in selected}
    rows: list[dict[str, Any]] = []
    for item in candidates:
        if str(item.get("exercise_key") or "") in selected_keys:
            continue
        rows.append(_with_student_context(item, variables, 0.0))
        if len(rows) + len(selected) >= limit:
            break
    return rows


def _exercise(
    key: str,
    title: str,
    target: str,
    primary: list[str],
    secondary: list[str],
    how_to: str,
    steps: list[str],
    evidence: list[str],
    video: dict[str, str],
    *,
    sets: str = "4",
    reps: str = "4회",
    load: str = "체중",
    rest: int = 90,
    progression: str = "1-2주는 품질을 맞추고, 3-4주는 실제 기록 리듬으로 연결한다.",
    kind: str | None = None,
) -> dict[str, Any]:
    exercise_kind = kind or _default_kind(key)
    return {
        "exercise_key": key,
        "title": title,
        "kind": exercise_kind,
        "kind_label": _KIND_LABELS.get(exercise_kind, "기술 전이"),
        "target": target,
        "primary_variables": primary,
        "secondary_variables": secondary,
        "how_to": how_to,
        "method_steps": steps,
        "common_mistake": "속도를 올리다가 착지나 몸통 정렬이 무너지면 강도를 낮춘다.",
        "dosage": {"sets": sets, "reps_or_time": reps, "load": load, "rest_seconds": rest, "progression": progression},
        "evidence_groups": evidence,
        "video": video,
    }


def _default_kind(key: str) -> str:
    if key in _STATIC_CORRECTIVE_KEYS:
        return "static_corrective"
    if key in _DYNAMIC_CORRECTIVE_KEYS:
        return "dynamic_corrective"
    if key in _EVENT_DRILL_KEYS:
        return "event_drill"
    return "technical_transfer"


def _video(video_id: str, title: str, channel: str) -> dict[str, str]:
    return {
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": title,
        "channel": channel,
        "verified_at": _VERIFIED_AT,
        "verification": _VERIFY_METHOD,
    }


_EXERCISES: dict[str, list[dict[str, Any]]] = {
    "standing_long_jump": [
        _exercise("fast_reversal_cmj", "멈추지 않는 반동 점프", "transition_speed", ["takeoff_transition_time", "descent_velocity"], ["vertical_velocity", "com_descent_distance"], "앉은 뒤 멈추지 않고 바로 밀어 전환시간을 줄인다.", ["발은 골반 너비로 선다.", "짧게 앉자마자 바로 뛴다.", "착지 후 2초 정지한다."], ["countermovement"], _video("Jb63W4LQ8Ak", "Countermovement Jump - Demonstration + Progressions", "Strength-Forge"), sets="5", reps="3회"),
        _exercise("snap_down_to_jump", "스냅다운 후 바로 점프", "transition_speed", ["descent_velocity", "takeoff_transition_time"], ["knee_peak_angular_velocity", "ankle_peak_angular_velocity", "com_descent_distance"], "빠르게 내려가며 하체를 준비하고 바로 점프로 연결한다.", ["팔을 위에서 아래로 빠르게 내린다.", "무릎이 안쪽으로 무너지지 않게 멈춘다.", "멈춤이 길어지기 전 바로 점프한다."], ["countermovement"], _video("vQqmduv_de8", "Snapdown to Jump and Stick", "The Active Life")),
        _exercise("pogo_jump", "발목 탄성 포고 점프", "transition_speed", ["ankle_peak_angular_velocity", "takeoff_transition_time"], ["descent_velocity"], "발목 반응을 빠르게 만들어 바닥에 머무는 시간을 줄인다.", ["무릎을 크게 굽히지 않는다.", "발목으로 짧게 튕긴다.", "상체는 길게 세운다."], ["countermovement", "ankle_mobility"], _video("j0nl5dWuqN4", "Pogo Jumps Tutorial - Proper Form and Technique", "Runna"), sets="4", reps="8초"),
        _exercise("depth_drop_rebound", "낮은 박스 리바운드 점프", "transition_speed", ["takeoff_transition_time", "vertical_velocity"], ["knee_peak_angular_velocity", "ankle_peak_angular_velocity", "com_descent_distance"], "착지 충격을 오래 끌지 않고 다시 뛰는 반응을 만든다.", ["낮은 박스에서 조용히 내려온다.", "바닥 접촉을 짧게 만든다.", "자세가 무너지면 높이를 낮춘다."], ["countermovement"], _video("ZFUjMcjyyPc", "Depth Drop Rebound", "Snow Beast Performance"), reps="3회"),
        _exercise("shallow_countermovement_jump", "얕은 반동 점프", "transition_speed", ["com_descent_distance", "takeoff_transition_time"], ["vertical_velocity"], "너무 깊게 앉아 늦어지는 학생에게 얕고 빠른 리듬을 만든다.", ["평소보다 조금만 앉는다.", "발바닥 전체로 바닥을 누른다.", "뛴 뒤 착지 자세를 확인한다."], ["countermovement"], _video("09yR5a4u-6A", "How To Counter Movement Jump", "Third Space London")),
        _exercise("horizontal_push_broad_jump", "수평으로 밀어 제멀", "horizontal_velocity_loss", ["horizontal_velocity", "takeoff_angle"], ["hip_peak_angular_velocity", "ankle_takeoff_angle"], "위로만 뜨지 않고 바닥을 뒤로 밀어 앞으로 나가는 힘을 만든다.", ["시선은 정면보다 살짝 위에 둔다.", "발로 바닥을 뒤로 민다.", "착지는 양발을 동시에 뻗는다."], ["biomechanics", "optimum_takeoff_angle"], _video("V106E7NX320", "How to Instantly Improve your BROAD JUMP", "Rising Lion"), sets="5", reps="3회"),
        _exercise("band_resisted_broad_jump", "밴드 저항 제멀", "horizontal_velocity_loss", ["horizontal_velocity", "hip_peak_angular_velocity"], ["takeoff_angle", "ankle_peak_angular_velocity", "ankle_takeoff_angle"], "허리나 팔이 아니라 다리로 앞으로 미는 감각을 만든다.", ["허리에 가벼운 밴드를 건다.", "몸이 접히지 않게 앞으로 민다.", "거리는 80%부터 시작한다."], ["biomechanics"], _video("XWNlgXVV1Ro", "Band Resisted Broad Jumps", "Baxter Basics Group Personal Training"), reps="3회", load="가벼운 밴드"),
        _exercise("split_squat_horizontal_push", "스플릿 스쿼트 점프", "horizontal_velocity_loss", ["horizontal_velocity", "knee_peak_angular_velocity"], ["hip_peak_angular_velocity", "knee_takeoff_angle"], "한쪽 다리로 바닥을 뒤로 미는 힘을 키운다.", ["앞발 뒤꿈치가 뜨지 않게 선다.", "무릎과 발끝 방향을 맞춘다.", "위보다 앞으로 밀어낸다."], ["biomechanics"], _video("rQVUltB7aUc", "How to Do the Split Squat Jump", "Absolute MMA"), sets="4", reps="5회/측"),
        _exercise("broad_jump_stick_landing", "제멀 후 정지 착지", "horizontal_velocity_loss", ["horizontal_velocity", "com_foot_distance"], ["takeoff_angle", "flight_hip_min_angle", "flight_knee_min_angle"], "앞으로 나가면서도 착지에서 기록을 잃지 않는 제어를 만든다.", ["70-80% 거리로 뛴다.", "발을 앞으로 뻗고 손은 짚지 않는다.", "착지 후 2초 버틴다."], ["landing", "biomechanics"], _video("nmvGGDL5G3g", "Broad Jump stick landing", "Body Art Athletics"), reps="3회"),
        _exercise("low_angle_projection_jump", "낮은 각도 보정 제멀", "horizontal_velocity_loss", ["takeoff_angle", "horizontal_velocity"], ["vertical_velocity", "ankle_takeoff_angle"], "이륙각이 너무 낮거나 높은 학생의 앞-위 비율을 맞춘다.", ["첫 표식은 낮고 길게 둔다.", "두 번째 표식은 살짝 위로 민다.", "영상으로 이륙각을 확인한다."], ["optimum_takeoff_angle"], _video("dVgtvAXeBQw", "The Fundamentals - Standing Long Jump", "Athletics Coach"), reps="3회"),
        _exercise("hip_hinge_pre_jump", "힌지 후 제멀", "hip_drive", ["hip_peak_angular_velocity", "hip_takeoff_angle"], ["horizontal_velocity", "knee_takeoff_angle"], "엉덩이와 허벅지 뒤쪽으로 바닥을 미는 순서를 만든다.", ["엉덩이를 뒤로 접는다.", "가슴은 무너지지 않게 세운다.", "엉덩이를 펴며 앞으로 뛴다."], ["biomechanics"], _video("t4CV7g8byuk", "Hip Hinge: Broad Jump Analogy", "Testosterone Nation"), reps="4회"),
        _exercise("kettlebell_swing_hinge", "케틀벨 힙힌지 스윙", "hip_drive", ["hip_peak_angular_velocity"], ["horizontal_velocity", "descent_velocity", "hip_takeoff_angle"], "고관절을 빠르게 펴는 힘과 타이밍을 키운다.", ["팔로 들지 말고 엉덩이로 민다.", "등은 길게 유지한다.", "벨이 뜨면 힘을 빼고 다시 접는다."], ["biomechanics"], _video("e_DWz1ojlDY", "How to do a Kettlebell Swing for the Ultimate Hip Hinge", "Tiger Fitness"), reps="8회", load="가벼운 케틀벨"),
        _exercise("single_leg_hip_thrust", "한발 힙쓰러스트", "hip_drive", ["hip_peak_angular_velocity", "hip_takeoff_angle"], ["knee_peak_angular_velocity", "knee_takeoff_angle"], "엉덩이 힘이 약한 학생의 좌우 추진 안정성을 보강한다.", ["턱을 살짝 당긴다.", "허리 대신 엉덩이를 조인다.", "위에서 1초 멈춘다."], ["biomechanics"], _video("xKDhmWlf1UE", "Perfect Your Single Leg Hip Thrust", "Muscle & Motion"), sets="3", reps="6회/측", load="체중 또는 가벼운 원판"),
        _exercise("romanian_deadlift", "루마니안 데드리프트", "hip_drive", ["hip_peak_angular_velocity"], ["com_descent_distance", "descent_velocity", "hip_takeoff_angle"], "허벅지 뒤쪽과 엉덩이로 버티고 펴는 힘을 만든다.", ["무릎은 살짝 굽힌다.", "엉덩이를 뒤로 보내며 내려간다.", "허벅지 뒤쪽이 당기면 올라온다."], ["biomechanics"], _video("hQgFixeXdZo", "Dumbbell Romanian (RDL) Deadlift |TECHNIQUE for Beginners", "Mike | J2FIT Strength & Conditioning"), reps="6회", load="자세가 유지되는 낮은 부하"),
        _exercise("wall_drive_hip_extension", "벽 밀기 힙드라이브", "hip_drive", ["hip_peak_angular_velocity", "horizontal_velocity"], ["ankle_peak_angular_velocity", "hip_takeoff_angle", "ankle_takeoff_angle"], "고관절을 펴며 바닥을 뒤로 미는 느낌을 만든다.", ["양손으로 벽을 민다.", "몸을 일직선으로 기울인다.", "한쪽 다리로 바닥을 뒤로 강하게 민다."], ["biomechanics"], _video("uuFZ5eLDV10", "Sprint Wall Series - Acceleration Hip Load Drill", "Exercise Bioenergetics, Inc"), reps="5회/측"),
        _exercise("arm_swing_timing_jump", "팔스윙 타이밍 점프", "arm_swing", ["arm_backswing_angle", "arm_swing_peak_velocity"], ["takeoff_angle", "vertical_velocity"], "팔이 다리 펴지는 순간에 맞춰 앞으로 오게 만든다.", ["팔을 뒤로 준비한다.", "다리 펴는 순간 팔을 앞으로 보낸다.", "팔만 먼저 나가면 다시 천천히 한다."], ["arm_swing"], _video("36gEUko_Jt0", "Standing Long Jump With Arm Swing", "Nicole W"), reps="4회"),
        _exercise("no_arm_vs_arm_jump", "팔 없이-팔 사용 비교 점프", "arm_swing", ["arm_swing_peak_velocity", "arm_backswing_angle"], ["vertical_velocity"], "팔이 기록에 보태는 타이밍을 몸으로 비교한다.", ["첫 회는 손을 허리에 두고 뛴다.", "둘째 회는 팔을 사용한다.", "차이가 작으면 팔 타이밍을 다시 맞춘다."], ["arm_swing"], _video("SeYWLj9Jn7k", "The Effects of Arm Swing Mechanics in Broad Jump Velocity Testing", "Justin Ochoa"), reps="각 3회"),
        _exercise("medicine_ball_broad_jump", "메디신볼 전방 스윙 점프", "arm_swing", ["arm_backswing_angle", "arm_swing_peak_velocity"], ["hip_peak_angular_velocity", "horizontal_velocity"], "팔-몸통-하체가 한 번에 앞으로 이어지는 리듬을 만든다.", ["가벼운 볼을 가슴 앞에 든다.", "팔과 엉덩이를 같이 뒤로 준비한다.", "볼을 던지듯 앞으로 뛰어간다."], ["arm_swing", "biomechanics"], _video("4asP14DeUnY", "Medicine Ball Broad Jump", "Performa Fit Athletic Performance Training"), reps="4회", load="가벼운 메디신볼"),
        _exercise("standing_long_jump_arm_swing_fix", "제멀 팔스윙 리듬 보정", "arm_swing", ["arm_backswing_angle", "arm_swing_peak_velocity"], ["takeoff_angle", "vertical_velocity"], "팔 백스윙과 전방 스윙이 하체 신전 타이밍에 맞게 이어지도록 만든다.", ["팔을 허리 뒤 목표선까지 준비한다.", "다리가 펴지는 순간 팔을 앞으로 보낸다.", "점프 없이 2회 리듬을 맞춘 뒤 70% 강도로 연결한다."], ["arm_swing"], _video("36gEUko_Jt0", "Standing Long Jump With Arm Swing", "Nicole W"), reps="6회", load="추가 부하 없음"),
        _exercise("backswing_marker_jump", "팔 뒤준비 표식 점프", "arm_swing", ["arm_backswing_angle"], ["arm_swing_peak_velocity", "takeoff_angle", "vertical_velocity"], "팔을 너무 크게 빼거나 너무 작게 빼는 학생의 준비 각도를 맞춘다.", ["허리 뒤 표식을 정한다.", "팔이 표식을 지나치면 줄인다.", "표식에 맞춘 뒤 바로 점프한다."], ["arm_swing"], _video("dVgtvAXeBQw", "The Fundamentals - Standing Long Jump", "Athletics Coach"), reps="4회"),
        _exercise("jump_squat_light_load", "발목-무릎 빠른 신전 점프 스쿼트", "takeoff_result", ["vertical_velocity", "takeoff_angle"], ["knee_peak_angular_velocity", "ankle_peak_angular_velocity", "knee_takeoff_angle", "ankle_takeoff_angle"], "가벼운 부하로 발목과 무릎을 빠르게 펴는 힘을 만든다.", ["무게는 속도가 줄지 않는 정도만 든다.", "깊이보다 빠른 신전을 우선한다.", "착지 후 바로 자세를 멈춘다."], ["biomechanics"], _video("XOTO2qWRy9U", "Dumbbell Jump Squat | Exercise Guide", "Bodybuilding.com"), reps="3회", load="가벼운 덤벨"),
        _exercise("box_jump_soft_landing", "박스 점프 조용한 착지", "takeoff_result", ["vertical_velocity", "knee_peak_angular_velocity"], ["knee_takeoff_angle", "com_foot_distance"], "위로 뜨는 힘을 만들되 착지 제어를 같이 만든다.", ["낮은 박스를 쓴다.", "무릎과 발끝 방향을 맞춘다.", "소리 없이 착지한다."], ["landing", "biomechanics"], _video("eQqwXl44zNE", "Soft Landing Box Jump", "Athlete Academy"), reps="3회"),
        _exercise("takeoff_angle_marker_jump", "이륙각 표식 제멀", "takeoff_result", ["takeoff_angle", "horizontal_velocity"], ["vertical_velocity", "ankle_takeoff_angle"], "너무 낮게 밀거나 위로만 뜨는 패턴을 표식으로 교정한다.", ["바닥에 목표 착지선을 둔다.", "이륙 순간 몸이 너무 숙여지지 않게 한다.", "각도와 거리를 영상으로 확인한다."], ["optimum_takeoff_angle"], _video("V106E7NX320", "How to Instantly Improve your BROAD JUMP", "Rising Lion"), reps="3회"),
        _exercise("vertical_to_broad_jump", "위-앞 전환 점프", "takeoff_result", ["vertical_velocity", "horizontal_velocity"], ["takeoff_angle"], "위로 뜨는 힘과 앞으로 나가는 힘의 비율을 맞춘다.", ["첫 회는 위로 점프한다.", "둘째 회는 같은 힘으로 앞으로 뛴다.", "둘의 높이와 거리를 비교한다."], ["biomechanics", "optimum_takeoff_angle"], _video("uhz-ia-2UcM", "How To Do Broad Jumps", "PureGym"), reps="각 3회"),
        _exercise("kneeling_jump_to_broad", "무릎앉아 점프 후 제멀", "takeoff_result", ["hip_peak_angular_velocity", "vertical_velocity"], ["takeoff_angle"], "엉덩이와 무릎을 폭발적으로 펴는 순서를 만든다.", ["무릎앉아 자세에서 시작한다.", "엉덩이를 빠르게 펴며 선다.", "바로 작은 제멀로 연결한다."], ["biomechanics"], _video("xGtbZj9trDw", "Kneeling Jump To Broad Jump", "Brandon Smitley"), reps="3회"),
        _exercise("stick_landing", "정지 착지 연습", "landing_efficiency", ["com_foot_distance", "flight_knee_min_angle"], ["horizontal_velocity", "flight_hip_min_angle"], "발을 앞으로 뻗은 뒤 뒤로 넘어가지 않는 제어를 만든다.", ["짧은 거리로 뛴다.", "발을 앞으로 뻗고 무릎을 접는다.", "손을 짚지 않고 2초 버틴다."], ["landing"], _video("nmvGGDL5G3g", "Broad Jump stick landing", "Body Art Athletics"), reps="4회"),
        _exercise("eccentric_split_squat", "천천히 내려가는 스플릿 스쿼트", "landing_efficiency", ["flight_knee_min_angle", "com_foot_distance"], ["knee_peak_angular_velocity", "knee_takeoff_angle"], "착지 때 무릎을 접고 버티는 힘을 만든다.", ["3초 동안 천천히 내려간다.", "앞무릎이 안쪽으로 무너지지 않게 한다.", "올라올 때는 부드럽게 선다."], ["landing"], _video("tWMWstS9RXE", "How to perform: Eccentric split squat", "Cody Taggart Training"), reps="6회/측", load="천천히 버틸 수 있는 낮은 부하"),
        _exercise("towel_hamstring_curl", "수건 햄스트링 컬", "landing_efficiency", ["flight_hip_min_angle", "flight_knee_min_angle"], ["com_foot_distance", "knee_takeoff_angle"], "공중에서 다리를 당기고 착지 전 제어하는 허벅지 뒤쪽 힘을 만든다.", ["바닥에 누워 발뒤꿈치 아래 수건을 둔다.", "엉덩이를 들고 발을 천천히 멀리 보낸다.", "허리가 꺾이면 엉덩이를 낮추고 범위를 줄인다."], ["landing"], _video("cWSsWpuxmYM", "Towel Hamstring Curls", "Nick Brattain"), sets="3", reps="6-8회", load="수건 또는 슬라이더"),
        _exercise("leg_reach_stick_landing", "제멀 다리 당김 착지", "landing_efficiency", ["flight_hip_min_angle", "flight_knee_min_angle"], ["com_foot_distance", "knee_takeoff_angle"], "짧은 제멀에서 다리를 당긴 뒤 발을 앞으로 보내고 흔들림 없이 버틴다.", ["60-70% 거리로 작게 제멀을 뛴다.", "공중에서 무릎을 가볍게 당긴다.", "발을 앞으로 보내고 손 짚지 않고 2초 버틴다."], ["landing"], _video("nmvGGDL5G3g", "Broad Jump stick landing", "Body Art Athletics"), reps="3회"),
        _exercise("single_leg_rdl_balance", "한발 RDL 균형", "landing_efficiency", ["com_foot_distance"], ["hip_peak_angular_velocity", "flight_knee_min_angle", "flight_hip_min_angle"], "착지 후 몸이 뒤로 무너지지 않게 엉덩이와 균형 제어를 만든다.", ["한발로 선다.", "엉덩이를 뒤로 보내며 몸을 접는다.", "골반이 돌아가지 않게 돌아온다."], ["landing", "biomechanics"], _video("fY1502wXDQ4", "Bad Balance? Try this single leg Romanian Deadlift cues", "Lance Goyke"), sets="3", reps="6회/측"),
    ]
}
