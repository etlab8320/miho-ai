"""PACA API client for academy account login."""

from __future__ import annotations

from typing import Any

import httpx

from .auth_flow import AcademyLoginResult
from .paca_config import AcademyConfigError, resolve_paca_base_url


DEFAULT_PACA_BASE_URL = ""


class AcademyLoginError(RuntimeError):
    pass


def login_paca(
    *,
    email: str,
    password: str,
    base_url: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> AcademyLoginResult:
    try:
        resolved_base_url = resolve_paca_base_url(base_url)
    except AcademyConfigError as exc:
        raise AcademyLoginError(str(exc)) from exc
    url = f"{resolved_base_url}/paca/auth/login"
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, transport=transport) as client:
            response = client.post(url, json={"email": email, "password": password})
    except httpx.HTTPError as exc:
        raise AcademyLoginError("학원 서버에 연결하지 못했어. 잠시 후 다시 시도해줘.") from exc

    if response.status_code in {400, 401, 403}:
        raise AcademyLoginError("이메일이나 비밀번호가 맞지 않아.")
    if response.status_code >= 500:
        raise AcademyLoginError("학원 서버가 잠시 불안정해. 잠시 후 다시 시도해줘.")
    try:
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AcademyLoginError("로그인 응답을 확인하지 못했어. 잠시 후 다시 시도해줘.") from exc

    return _parse_login_payload(payload)


def _parse_login_payload(payload: dict[str, Any]) -> AcademyLoginResult:
    token = str(payload.get("token") or payload.get("accessToken") or "")
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    academy = user.get("academy") if isinstance(user.get("academy"), dict) else {}
    academy_id = user.get("academyId") or user.get("academy_id") or academy.get("id")
    if not token or not user or academy_id is None:
        raise AcademyLoginError("로그인 정보가 부족해. 관리자에게 확인해줘.")
    return AcademyLoginResult(
        token=token,
        user_id=str(user.get("id") or ""),
        email=str(user.get("email") or ""),
        name=str(user.get("name") or user.get("email") or "사용자"),
        role=str(user.get("role") or ""),
        academy_id=str(academy_id),
        academy_name=str(academy.get("name") or user.get("academyName") or "학원"),
    )
