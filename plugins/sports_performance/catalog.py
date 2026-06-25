"""Exercise catalog for PE entrance exam motion feedback."""

from __future__ import annotations

from typing import Any


EXERCISES: dict[str, dict[str, Any]] = {
    "standing_long_jump": {
        "name_ko": "제자리멀리뛰기",
        "aliases": ("제멀", "제자리멀리뛰기", "standing long jump", "long_jump"),
        "metrics": {
            "발사각": "launch_angle",
            "무릎각도": "knee_angle",
            "발목각도": "ankle_angle",
            "고관절각도": "hip_angle",
            "착지안정성": "landing_stability",
        },
        "checkpoints": ("발사각", "고관절-무릎-발목 신전", "팔스윙 타이밍", "착지 안정성"),
        "drills": ("암스윙 브로드점프 4x4", "스쿼트 점프 4x5", "스틱 랜딩 3x5"),
    },
    "medicine_ball_throw": {
        "name_ko": "메디신볼던지기",
        "aliases": ("메디", "메디신볼", "메디신볼던지기", "medicine ball"),
        "metrics": {
            "릴리즈각": "release_angle",
            "릴리즈높이": "release_height",
            "몸통회전": "trunk_rotation",
            "고관절신전": "hip_extension",
        },
        "checkpoints": ("하체-몸통-팔 연결", "릴리즈 각도", "릴리즈 높이", "몸통 회전"),
        "drills": ("스쿱 토스 4x5", "힙 드라이브 토스 4x4", "스텝-릴리즈 리듬 3x6"),
    },
    "shuttle_run": {
        "name_ko": "왕복달리기",
        "aliases": ("왕복", "왕복달리기", "10m왕복", "20m왕복", "shuttle run"),
        "metrics": {
            "방향전환각": "turn_angle",
            "접지시간": "contact_time",
            "감속거리": "deceleration_distance",
            "상체기울기": "trunk_lean",
        },
        "checkpoints": ("감속 자세", "방향전환 접지", "중심 이동", "재가속 첫걸음"),
        "drills": ("감속-스틱 4x3", "5-10-5 컷 드릴 4세트", "낮은 중심 재가속 4x4"),
    },
    "back_strength": {
        "name_ko": "배근력",
        "aliases": ("배근력", "back strength", "back_strength"),
        "metrics": {
            "무릎각도": "knee_angle",
            "고관절각도": "hip_angle",
            "몸통각도": "trunk_angle",
            "견갑고정": "scapular_set",
        },
        "checkpoints": ("고관절 힌지", "몸통 고정", "무릎 잠김 방지", "당기는 타이밍"),
        "drills": ("힙힌지 패턴 3x8", "밴드 로우 고정 3x10", "서브맥스 등척성 당기기 4x5초"),
    },
    "sit_and_reach": {
        "name_ko": "좌전굴",
        "aliases": ("좌전굴", "sit and reach", "sit_reach"),
        "metrics": {
            "골반각도": "pelvic_tilt",
            "허리굴곡": "lumbar_flexion",
            "햄스트링제한": "hamstring_limitation",
            "좌우비대칭": "asymmetry",
        },
        "checkpoints": ("골반 전방경사", "햄스트링 제한", "허리 말림", "좌우 비대칭"),
        "drills": ("동적 햄스트링 플로우 3x8", "골반 틸트 연습 3x10", "호흡 기반 전굴 4x20초"),
    },
}


def normalize_exercise(value: Any) -> dict[str, Any] | None:
    text = str(value or "").strip().lower().replace(" ", "")
    if not text:
        return None
    for key, data in EXERCISES.items():
        aliases = (key, *data["aliases"])
        if any(text == str(alias).lower().replace(" ", "") for alias in aliases):
            return {"key": key, "name_ko": data["name_ko"], "checkpoints": list(data["checkpoints"])}
    return None


def normalize_metrics(exercise_key: str, metrics: Any) -> dict[str, Any]:
    if not isinstance(metrics, dict):
        return {}
    aliases = EXERCISES[exercise_key]["metrics"]
    normalized: dict[str, Any] = {}
    for key, value in metrics.items():
        clean_key = str(key or "").strip()
        if not clean_key:
            continue
        normalized[aliases.get(clean_key, clean_key)] = value
    return normalized


def schema_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "schema_version": 1,
        "required": ["exercise", "metrics"],
        "optional": ["student_name", "student_query"],
        "exercises": {
            key: {
                "name_ko": value["name_ko"],
                "aliases": list(value["aliases"]),
                "metrics": value["metrics"],
                "checkpoints": list(value["checkpoints"]),
            }
            for key, value in EXERCISES.items()
        },
    }
