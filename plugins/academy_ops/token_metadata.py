"""Unverified PACA JWT metadata used for local binding safety checks."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any


ACADEMY_BINDING_ERROR_MESSAGE = "학원 계정 정보를 확인하지 못했어. 관리자에게 문의해줘."
TOKEN_EXPIRED_MESSAGE = "학원 계정 연결을 다시 확인해줘. `/academy login`으로 새로 연결해줘."


@dataclass(frozen=True)
class TokenMetadata:
    academy_id: str = ""
    expires_at: int | None = None


def decode_token_metadata(token: str) -> TokenMetadata:
    payload = _jwt_payload(token)
    if not payload:
        return TokenMetadata()
    return TokenMetadata(
        academy_id=_academy_id(payload),
        expires_at=_expires_at(payload.get("exp")),
    )


def binding_token_error(token: str, *, academy_id: str, now: int | None = None) -> str:
    metadata = decode_token_metadata(token)
    if _is_expired(metadata.expires_at, now=now):
        return TOKEN_EXPIRED_MESSAGE
    if metadata.academy_id and metadata.academy_id != str(academy_id):
        return ACADEMY_BINDING_ERROR_MESSAGE
    return ""


def assert_token_matches_binding(token: str, *, academy_id: str, now: int | None = None) -> TokenMetadata:
    metadata = decode_token_metadata(token)
    if _is_expired(metadata.expires_at, now=now):
        raise ValueError(TOKEN_EXPIRED_MESSAGE)
    if metadata.academy_id and metadata.academy_id != str(academy_id):
        raise ValueError(ACADEMY_BINDING_ERROR_MESSAGE)
    return metadata


def _jwt_payload(token: str) -> dict[str, Any]:
    parts = str(token or "").split(".")
    if len(parts) < 2:
        return {}
    try:
        raw = _b64decode(parts[1])
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _academy_id(payload: dict[str, Any]) -> str:
    direct = payload.get("academyId") or payload.get("academy_id")
    if direct is not None:
        return str(direct)
    academy = payload.get("academy") if isinstance(payload.get("academy"), dict) else {}
    if academy.get("id") is not None:
        return str(academy["id"])
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    nested = user.get("academyId") or user.get("academy_id")
    return str(nested) if nested is not None else ""


def _expires_at(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_expired(expires_at: int | None, *, now: int | None = None) -> bool:
    return expires_at is not None and expires_at <= int(now or time.time())
