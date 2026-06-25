"""Keyword policy for PE-brain sports evidence classification."""

from __future__ import annotations

ALLOWED_PE_BRAIN_CATEGORIES = {"physical", "mental"}

EXERCISE_TERMS: dict[str, tuple[str, ...]] = {
    "standing_long_jump": (
        "standing long jump",
        "long jump",
        "horizontal jump",
        "broad jump",
        "slj",
        "jump",
        "jumping",
        "plyometric",
        "하체 폭발",
        "수평 파워",
        "제자리멀리뛰기",
        "점프",
        "플라이오메트릭",
    ),
    "medicine_ball_throw": (
        "medicine ball",
        "upper body explosive",
        "upper-body power",
        "upper body power",
        "throw",
        "투척",
        "메디신볼",
        "상체 파워",
    ),
    "shuttle_run": (
        "shuttle",
        "change of direction",
        "505 test",
        "agility",
        "sprint",
        "acceleration",
        "deceleration",
        "왕복",
        "민첩",
        "방향 전환",
        "가속",
        "감속",
    ),
    "back_strength": (
        "back strength",
        "trunk strength",
        "isometric",
        "hip hinge",
        "deadlift",
        "등 근력",
        "배근력",
        "몸통 근력",
    ),
    "sit_and_reach": (
        "sit and reach",
        "flexibility",
        "hamstring",
        "mobility",
        "좌전굴",
        "유연성",
        "햄스트링",
        "가동성",
    ),
}

MENTAL_TERMS = (
    "mental toughness",
    "self-efficacy",
    "burnout",
    "choking",
    "goal setting",
    "imagery",
    "confidence",
    "멘탈",
    "자기 효능감",
    "목표 설정",
    "심상",
)

SPORTS_TERMS = (
    "athlete",
    "sport",
    "sports",
    "training",
    "performance",
    "physical education",
    "운동선수",
    "스포츠",
    "훈련",
    "수행",
    "체육",
)

OFF_DOMAIN_TERMS = (
    "스포츠 심리학 논문이 아니라",
    "스포츠 심리학 논문이 아닌",
    "산부인과",
    "임산부",
    "간 효소",
    "출산 결과",
    "drug delivery",
    "약물 전달",
    "암 치료",
    "환경 심리학",
    "eco-connections",
    "청각 피드백",
    "음성 운동 제어",
)
