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
