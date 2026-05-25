"""Natural-language trigger detection for academy account binding."""

from __future__ import annotations

from dataclasses import dataclass


DIRECT_COMPOUNDS = (
    "학원관리",
    "학생관리",
    "출석조회",
    "성적조회",
    "파카연동",
    "피크연동",
)
ACADEMY_TERMS = (
    "학원",
    "학생",
    "수강생",
    "원생",
    "출석",
    "출결",
    "성적",
    "기록",
    "상담",
    "학원비",
    "납부",
    "결제",
    "운동계획",
    "수업계획",
)
SYSTEM_TERMS = ("paca", "peak", "파카", "피크")
INTENT_TERMS = (
    "관리",
    "연동",
    "연결",
    "로그인",
    "붙여",
    "세팅",
    "조회",
    "보여",
    "해줘",
    "하고싶",
    "하고 싶",
)


@dataclass(frozen=True)
class AcademyTrigger:
    should_prompt: bool
    confidence: float
    reason: str


def detect_academy_trigger(text: str) -> AcademyTrigger:
    normalized = _normalize(text)
    if not normalized or normalized.startswith("/"):
        return AcademyTrigger(False, 0.0, "empty_or_command")

    compact = normalized.replace(" ", "")
    if any(term in compact for term in DIRECT_COMPOUNDS):
        return AcademyTrigger(True, 0.96, "direct_compound")

    system_hits = _count_hits(normalized, SYSTEM_TERMS)
    academy_hits = _count_hits(normalized, ACADEMY_TERMS)
    intent_hits = _count_hits(normalized, INTENT_TERMS)

    score = min(0.98, (system_hits * 0.42) + (academy_hits * 0.24) + (intent_hits * 0.22))
    should_prompt = score >= 0.62 or (system_hits > 0 and intent_hits > 0)
    reason = "system_intent" if system_hits else "academy_intent"
    return AcademyTrigger(should_prompt, score, reason)


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _count_hits(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)
