"""Tool entrypoint for Discord student-card image generation."""

from __future__ import annotations

from datetime import date
import json
import os
from typing import Any

from .academy_api import AcademyApiClient, AcademyApiError
from .auth_store import decrypt_token, get_binding
from .context import current_discord_user_id, infer_student_query_from_current_request
from .paca_client import DEFAULT_PACA_BASE_URL
from .student_card import (
    AcademyClient,
    AcademyStudentCardService,
    StudentCardError,
)
from .student_card_renderer import StudentCardImageRenderer, StudentCardRenderError


def _student_card_image_tool_handler(
    args: dict[str, Any] | None = None,
    **kwargs: Any,
) -> str:
    payload = args or {}
    student_query = str(payload.get("student_query") or "").strip() or infer_student_query_from_current_request()
    period_days = _int_arg(payload.get("period_days"), default=14)
    today = _date_arg(payload.get("today"))
    if not student_query:
        return _json_error("학생 이름이나 검색어를 알려줘.")

    client = kwargs.get("client")
    renderer = kwargs.get("renderer")
    has_injected_runtime = client is not None and renderer is not None
    token = ""
    if not has_injected_runtime:
        discord_user_id = current_discord_user_id()
        if not discord_user_id:
            return _json_error("디스코드 사용자 정보를 확인하지 못했어. 디스코드에서 다시 요청해줘.")
        binding = get_binding(discord_user_id)
        if binding is None:
            return _json_error("학원 계정 연결이 필요해. `/academy login`으로 먼저 연결해줘.")
        token = decrypt_token(binding.token_ciphertext) or ""
        if not token:
            return _json_error("학원 계정 연결을 복호화하지 못했어. `/academy login`으로 다시 연결해줘.")

    if client is None:
        client = AcademyApiClient(
            token=token,
            base_url=os.getenv("MIHO_ACADEMY_PACA_BASE_URL", DEFAULT_PACA_BASE_URL),
        )
    renderer = renderer or StudentCardImageRenderer()
    try:
        card = AcademyStudentCardService(_typed_client(client)).build(
            student_query,
            today=today,
            period_days=period_days,
        )
        image_path = renderer.render(card)
    except (AcademyApiError, StudentCardError, StudentCardRenderError) as exc:
        return _json_error(str(exc))

    media_tag = f"MEDIA:{image_path}"
    message = f"{card.profile.name} 학생 카드야. 민감정보는 이미지에 넣지 않았어. {media_tag}"
    return json.dumps(
        {
            "ok": True,
            "message": message,
            "image_path": str(image_path),
            "media_tag": media_tag,
            "summary_text": card.risk.judgment,
            "assistant_guidance": {
                "persona_commentary": True,
                "avoid_hardcoded_judgment": True,
                "instruction": "이미지는 사실 기반 카드이고, 답변 문장은 card의 출결/기록/위험 신호를 보고 미호 말투로 작성해.",
            },
            "missing_sources": card.missing_sources,
            "card": card.to_public_dict(),
        },
        ensure_ascii=False,
    )


def _typed_client(client: Any) -> AcademyClient:
    return client


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


def _int_arg(value: Any, *, default: int) -> int:
    try:
        return max(1, min(int(value), 60))
    except (TypeError, ValueError):
        return default


def _date_arg(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
