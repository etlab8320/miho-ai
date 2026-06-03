"""Payload parsing helpers for academy natural routing."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


def response_content(response: Any) -> str:
    try:
        return str(response.choices[0].message.content or "")
    except (AttributeError, IndexError, TypeError):
        return str(response or "")


def load_payload(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines).strip()
    try:
        payload = json.loads(clean)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def payload_message(payload: dict[str, Any]) -> str:
    return str(payload.get("message") or "조회 결과를 정리하지 못했어.")


def is_login_required_payload(payload: dict[str, Any]) -> bool:
    if payload.get("ok") is not False:
        return False
    message = str(payload.get("message") or "")
    return "/academy login" in message or "학원 계정 연결" in message


def today_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


def tool_timeout_message() -> str:
    return "PACA/Peak API 조회가 제한시간을 넘겨서 중단했어. 잠시 뒤 다시 시도해줘."
