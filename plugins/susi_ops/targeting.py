"""Recommendation target filtering rules for 2027 susi 체대입시."""

from __future__ import annotations

import json
from typing import Any

from .db import _json_loads


_CONDITION_LIMITED_TRACK_KEYWORDS = (
    "농어촌", "기회균형", "기균", "특성화", "사회배려", "지역균형", "지역인재",
    "저소득", "기초생활", "차상위", "보훈", "장애", "목회자",
)
_CONDITION_TRACK_ALIASES = (
    ("농어촌",),
    ("기회균형", "기균"),
    ("특성화",),
    ("사회배려",),
    ("지역균형", "지역인재", "지역"),
    ("저소득", "기초생활", "차상위"),
    ("보훈",),
    ("장애",),
    ("목회자",),
)
_ATHLETIC_DEPARTMENT_KEYWORDS = (
    "체육", "스포츠", "운동", "레저", "골프", "건강관리", "재활",
    "트레이닝", "경호", "경찰",
)
_NON_TARGET_ART_DEPARTMENT_KEYWORDS = (
    "디자인", "미술", "회화", "만화", "게임", "그래픽", "영상", "영화",
    "연극", "음악", "국악", "보컬", "작곡", "기악", "피아노", "사진",
    "패션", "뷰티", "공연",
)
_NON_TARGET_DEPARTMENT_KEYWORDS = ("태권", "무도")
_NON_TARGET_TRACK_KEYWORDS = ("특기자", "경기실적")
_PROTECTION_DEPARTMENT_KEYWORDS = ("경호", "경찰")
_SPECIFIC_SPORT_EVENT_KEYWORDS = (
    "야구", "축구", "농구", "배구", "육상", "검도", "골프", "탁구", "테니스", "배드민턴",
    "복싱", "소프트볼", "양궁", "사격", "레슬링", "유도", "핸드볼", "하키",
)
_SPECIFIC_SPORT_SELECTION_KEYWORDS = ("종목별", "포지션", "경기실적", "단체종목", "개인종목", "선택한 1개 종목")


def _is_restricted_record_only_track(track: str) -> bool:
    return any(keyword in str(track or "") for keyword in _CONDITION_LIMITED_TRACK_KEYWORDS)


def _is_blocked_official_row(confidence: str, score_logic_json: Any) -> bool:
    if "absent_row" in str(confidence or ""):
        return True
    score_logic = _json_loads(score_logic_json, {}) or {}
    readiness = str(score_logic.get("calculation_readiness") or "")
    scope = str(score_logic.get("calculation_scope") or "")
    return (
        readiness == "not_in_2027_official_guide"
        or readiness.startswith("non_calculation_track")
        or scope == "do_not_calculate_absent_row"
    )


def _is_allowed_recommendation_target(department: str, track: str, requested_track: Any = None) -> bool:
    dept = str(department or "")
    trk = str(track or "")
    req = str(requested_track or "")
    is_protection_major = any(keyword in dept for keyword in _PROTECTION_DEPARTMENT_KEYWORDS)
    is_athletic_major = is_protection_major or any(keyword in dept for keyword in _ATHLETIC_DEPARTMENT_KEYWORDS)
    if not is_athletic_major:
        return False
    if any(keyword in dept for keyword in _NON_TARGET_ART_DEPARTMENT_KEYWORDS) and not is_athletic_major:
        return False
    if any(keyword in dept for keyword in _NON_TARGET_DEPARTMENT_KEYWORDS) and not is_protection_major:
        return False
    if any(keyword in trk for keyword in _NON_TARGET_TRACK_KEYWORDS):
        return False
    for aliases in _CONDITION_TRACK_ALIASES:
        if any(alias in trk for alias in aliases):
            return bool(req and any(alias in req for alias in aliases))
    return True


def _is_specific_sport_practical_row(practical_events_json: Any) -> bool:
    payload = _json_loads(practical_events_json, None)
    if not isinstance(payload, dict) or not payload.get("events"):
        return False
    text = json.dumps(payload, ensure_ascii=False)
    return (
        any(keyword in text for keyword in _SPECIFIC_SPORT_EVENT_KEYWORDS)
        and any(keyword in text for keyword in _SPECIFIC_SPORT_SELECTION_KEYWORDS)
    )
