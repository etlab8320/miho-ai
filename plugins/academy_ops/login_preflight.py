"""Fast routing for natural-language academy login binding requests."""

from __future__ import annotations

from typing import Any

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


def is_academy_login_request(text: str) -> bool:
    normalized = _compact(text)
    if not normalized or not _contains_any(normalized, LOGIN_MARKERS):
        return False
    if not _contains_any(normalized, ACADEMY_MARKERS) or is_academy_login_status_request(text):
        return False
    return _contains_any(normalized, LOGIN_REQUEST_MARKERS)


def is_academy_login_status_request(text: str) -> bool:
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
