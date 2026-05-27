"""Fast routing for natural-language academy login binding requests."""

from __future__ import annotations

from typing import Any

ACADEMY_MARKERS = ("paca", "peak", "파카", "피크", "학원", "학원관리", "academy")
LOGIN_MARKERS = ("로그인", "연결", "연동", "인증", "계정", "바인딩", "login", "connect", "link")
LOGIN_STATUS_MARKERS = ("했어", "했는데", "완료", "됐", "되었", "확인", "connected", "done", "success")


def is_academy_login_request(text: str) -> bool:
    normalized = _compact(text)
    if not normalized or not _contains_any(normalized, LOGIN_MARKERS):
        return False
    return _contains_any(normalized, ACADEMY_MARKERS)


def is_academy_login_status_request(text: str) -> bool:
    normalized = _compact(text)
    if not normalized or not _contains_any(normalized, LOGIN_MARKERS):
        return False
    return _contains_any(normalized, LOGIN_STATUS_MARKERS)


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
