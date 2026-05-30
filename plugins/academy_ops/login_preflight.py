"""Fast routing for natural-language academy login binding requests.

Intent detection prefers embedding-based semantic routing
(:mod:`plugins.academy_ops.semantic_intents`). It falls back to the historical
keyword logic only when no semantic embedding provider is available, routing is
disabled, or the match is ambiguous — so behaviour is unchanged whenever
embeddings are unavailable (e.g. CI without ``VOYAGE_API_KEY``).
"""

from __future__ import annotations

from typing import Any

from . import semantic_intents

# EMERGENCY FALLBACK ONLY — keyword markers used solely when semantic_intents
# returns None (no embedding provider / routing disabled / ambiguous). The
# primary intent path is embedding similarity over LOGIN_INTENTS below; these
# substrings must never be the primary classifier. Do not add keyword lists
# like these as a primary routing path (see test_academy_no_hardcoded_nlp).
ACADEMY_MARKERS = ("paca", "peak", "파카", "피크", "학원", "학원관리", "academy")
LOGIN_MARKERS = ("로그인", "연결", "연동", "인증", "계정", "바인딩", "login", "connect", "link")
LOGIN_REQUEST_MARKERS = (
    "로그인하자",
    "로그인해줘",
    "로그인링크",
    "로그인연결",
    "계정연결",
    "계정연동",
    "연결해줘",
    "연동해줘",
    "바인딩해줘",
    "loginplease",
    "loginlink",
    "connectaccount",
    "linkaccount",
)
LOGIN_STATUS_MARKERS = (
    "했어",
    "했는데",
    "완료",
    "됐",
    "돼",
    "되었",
    "되어",
    "상태",
    "확인",
    "connected",
    "done",
    "success",
)

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
        return _keyword_is_login_request(text)
    return label == "login_request"


def is_academy_login_status_request(text: str) -> bool:
    label = _semantic_login(text)
    if label is None:
        return _keyword_is_login_status_request(text)
    return label == "login_status"


def _keyword_is_login_request(text: str) -> bool:
    normalized = _compact(text)
    if not normalized or not _contains_any(normalized, LOGIN_MARKERS):
        return False
    if not _contains_any(normalized, ACADEMY_MARKERS) or _keyword_is_login_status_request(text):
        return False
    return _contains_any(normalized, LOGIN_REQUEST_MARKERS)


def _keyword_is_login_status_request(text: str) -> bool:
    normalized = _compact(text)
    if not normalized or not _contains_any(normalized, LOGIN_MARKERS):
        return False
    return _contains_any(normalized, LOGIN_STATUS_MARKERS)


def has_academy_login_context(text: str) -> bool:
    normalized = _compact(text)
    return _contains_any(normalized, LOGIN_MARKERS) and _contains_any(normalized, ACADEMY_MARKERS)


def is_gateway_source_authorized(gateway: Any, source: Any) -> bool:
    checker = getattr(gateway, "_is_user_authorized", None)
    if not callable(checker):
        return False
    try:
        return bool(checker(source))
    except Exception:
        return False


def _compact(text: str) -> str:
    return "".join(str(text or "").lower().split())


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(_compact(marker) in text for marker in markers)
