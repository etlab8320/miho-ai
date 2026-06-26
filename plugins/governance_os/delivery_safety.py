"""Shared safety matchers for Governance OS final delivery."""

from __future__ import annotations

import re
from typing import Any

from .delivery_gate_constants import (
    GOVERNANCE_JSON_LEAK_KEYS,
    GOVERNANCE_JSON_LEAK_PAIRS,
    INTERNAL_GUARD_LEAK_MARKERS,
)

HARD_INTERNAL_LEAK_MARKERS = (
    "확인 근거가 충분하지 않아",
    "확인 근거를 다시 모아",
    "확정 점수나 첨부 완료처럼 검증이 필요한 결과",
    "그대로 전달하지 않겠습니다",
    "필요한 확인을 다시 거쳐 이어서",
    "최종 전달할 수 없습니다",
    "확인할 근거가 없어",
    "전달하긴 어려워",
)
NON_RESULT_DEFERRAL_MARKERS = (
    "확인 후",
    "확인한 뒤",
    "확인된 뒤",
    "검증 후",
    "검증 뒤",
    "검증한 뒤",
    "검증된 뒤",
    "다시 확인",
    "확정본이 확인되면",
    "자료 보내주면",
    "자료를 보내주면",
    "원본 보내주면",
    "원본을 보내주면",
    "준비하겠습니다",
    "진행 중",
    "잠시만",
    "기다려 주세요",
)

_INVISIBLE_RE = re.compile(r"[​‌‍‎‏‪-‮⁠﻿]")


def normalized_blob(text: Any) -> str:
    """Casefold + collapse whitespace + strip invisible/bidi chars for matching."""

    return " ".join(_INVISIBLE_RE.sub("", str(text or "")).casefold().split())


def contains_hard_internal_leak(response_text: str) -> bool:
    blob = normalized_blob(response_text)
    return bool(blob and any(marker.casefold() in blob for marker in HARD_INTERNAL_LEAK_MARKERS))


def contains_internal_guard_leak(response_text: str) -> bool:
    blob = normalized_blob(response_text)
    if not blob:
        return False
    if contains_hard_internal_leak(response_text):
        return True
    if any(marker.casefold() in blob for marker in INTERNAL_GUARD_LEAK_MARKERS):
        return True
    if any(key.casefold() in blob for key in GOVERNANCE_JSON_LEAK_KEYS):
        return True
    return any(
        left.casefold() in blob and right.casefold() in blob
        for left, right in GOVERNANCE_JSON_LEAK_PAIRS
    )


def contains_non_result_deferral(response_text: str) -> bool:
    """True when a candidate says it will answer later instead of answering now."""

    blob = normalized_blob(response_text)
    if not blob or "media:" in blob or "첨부 파일 형식:" in blob:
        return False
    return any(marker.casefold() in blob for marker in NON_RESULT_DEFERRAL_MARKERS)
