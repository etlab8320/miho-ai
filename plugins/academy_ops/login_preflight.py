"""Fast routing for natural-language academy login binding requests.

Intent detection uses embedding-based semantic routing
(:mod:`plugins.academy_ops.semantic_intents`). When the embedding provider is
unavailable, routing is disabled, or the match is ambiguous, semantic_intents
returns None and no override is applied (allow).
"""

from __future__ import annotations

from typing import Any

from . import semantic_intents

# Example utterances per intent for semantic matching. These are anchors for
# embedding similarity, NOT substring keywords — new phrasings are matched by
# meaning, so this list need not enumerate every possible wording.
LOGIN_INTENT_GROUP = "academy_login"
LOGIN_INTENTS: dict[str, tuple[str, ...]] = {
    "login_request": (
        "학원 로그인하고 싶어",
        "파카 로그인해줘",
        "피크 계정 연결해줘",
        "학원관리 로그인 연결해줘",
        "학원 계정 연동해줘",
        "로그인 링크 보내줘",
        "파카 바인딩해줘",
        "로긴 좀 시켜줘",
        "학원 계정이랑 연결시켜줘",
        "paca login please",
        "link my academy account",
    ),
    "login_status": (
        "학원 로그인 됐어?",
        "파카 로그인되어있어?",
        "계정 연결됐는지 확인해줘",
        "피크 인증 상태 알려줘",
        "로그인 완료됐어 확인해줘",
        "학원 연동 잘 됐나?",
        "is my academy account connected?",
    ),
    "none": (
        "오늘 학생 출결 보여줘",
        "학생 관리카드 만들어줘",
        "내일 수업 일정 알려줘",
        "이번달 시험 성적 정리해줘",
        "안녕 미호야",
        "학생 카드 디자인 의견 줘",
        "파카 로그인 관련 구조 얘기해줘",
    ),
}

_last_login: dict[str, Any] = {"text": None, "label": None, "hit": False}


def _semantic_login(text: str) -> str | None:
    """Semantic intent for *text*, with a 1-entry cache.

    ``is_academy_login_status_request`` and ``is_academy_login_request`` are
    called back-to-back on the same message; caching avoids a second embedding
    round-trip for the same text.
    """
    key = text or ""
    if _last_login["hit"] and _last_login["text"] == key:
        return _last_login["label"]
    label = semantic_intents.classify(
        key, LOGIN_INTENT_GROUP, LOGIN_INTENTS, negative_label="none", min_margin=0.04
    )
    _last_login["text"] = key
    _last_login["label"] = label
    _last_login["hit"] = True
    return label


def is_academy_login_request(text: str) -> bool:
    label = _semantic_login(text)
    if label is None:
        return False
    return label == "login_request"


def is_academy_login_status_request(text: str) -> bool:
    label = _semantic_login(text)
    if label is None:
        return False
    return label == "login_status"


def has_academy_login_context(text: str) -> bool:
    label = _semantic_login(text)
    if label is None:
        return False
    return label in ("login_request", "login_status")


def is_gateway_source_authorized(gateway: Any, source: Any) -> bool:
    checker = getattr(gateway, "_is_user_authorized", None)
    if not callable(checker):
        return False
    try:
        return bool(checker(source))
    except Exception:
        return False
