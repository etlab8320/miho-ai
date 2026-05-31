"""Tool handlers for per-academy brand logo (report/card stamp) replacement."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .auth_store import get_binding
from .brand_assets import (
    delete_academy_logo,
    save_academy_logo,
    stored_academy_logo_path,
)
from .context import current_discord_user_id, current_event_context
from .response_guidance import academy_response_guidance


def _academy_set_brand_logo_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    academy_id = _resolve_academy_id(kwargs)
    if not academy_id["ok"]:
        return _json_error(str(academy_id["message"]))

    image_bytes = kwargs.get("image_bytes")
    if image_bytes is None:
        image_bytes = _read_attached_image_bytes()
    if not image_bytes:
        return _json_error(
            "로고로 쓸 이미지를 메시지에 첨부해줘. 이미지를 붙이고 '로고 이걸로 바꿔줘'라고 말해줘."
        )

    try:
        saved = save_academy_logo(academy_id["academy_id"], image_bytes)
    except ValueError as exc:
        return _json_error(str(exc))

    message = "학원 로고를 새 이미지로 바꿨어. 이제 리포트랑 학생카드 이미지에 이 로고가 찍혀 나올 거야."
    return json.dumps(
        {
            "ok": True,
            "operation": "brand.logo_set",
            "message": message,
            "logo_path": str(saved),
            "assistant_guidance": academy_response_guidance(),
        },
        ensure_ascii=False,
    )


def _academy_reset_brand_logo_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    academy_id = _resolve_academy_id(kwargs)
    if not academy_id["ok"]:
        return _json_error(str(academy_id["message"]))

    removed = delete_academy_logo(academy_id["academy_id"])
    if removed:
        message = "학원 로고를 지웠어. 이제 기본 로고로 리포트랑 카드 이미지가 나올 거야."
    else:
        message = "지정된 학원 로고가 없어서 기본 로고를 그대로 쓰고 있어."
    return json.dumps(
        {
            "ok": True,
            "operation": "brand.logo_reset",
            "message": message,
            "removed": removed,
            "assistant_guidance": academy_response_guidance(),
        },
        ensure_ascii=False,
    )


def register_brand_logo_tools(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_set_brand_logo",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_academy_set_brand_logo_tool_handler,
        description=(
            "Replace this academy's brand logo (the stamp on report and student-card images) "
            "with the image the user attached in the current message. "
            "Use when the user attaches an image and asks to change/set the logo (로고 바꿔/교체/이걸로). "
            "Reads the attached image from the message; takes no arguments."
        ),
    )
    ctx.register_tool(
        name="academy_reset_brand_logo",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_academy_reset_brand_logo_tool_handler,
        description=(
            "Remove this academy's custom brand logo so report and student-card images fall back "
            "to the default stamp. Use when the user asks to reset/remove the logo (로고 기본/원래대로/삭제)."
        ),
    )


def _read_attached_image_bytes() -> bytes | None:
    """Return the bytes of the first image attached to the current message.

    Discord caches inbound image attachments to local files and exposes them on
    the event as ``media_urls`` (paired with ``media_types``); we read the first
    image-typed entry. Returns None when there is no usable image attachment.
    """
    event = current_event_context()
    if event is None:
        return None
    media_urls = list(getattr(event, "media_urls", None) or [])
    media_types = list(getattr(event, "media_types", None) or [])
    for index, raw_url in enumerate(media_urls):
        mime = media_types[index] if index < len(media_types) else ""
        if not str(mime).startswith("image/"):
            continue
        local = _local_path(str(raw_url))
        if local is not None and local.is_file():
            try:
                return local.read_bytes()
            except OSError:
                return None
    return None


def _local_path(raw_url: str) -> Path | None:
    url = raw_url.strip()
    if not url:
        return None
    if url.startswith("file://"):
        url = url[len("file://"):]
    elif url.startswith(("http://", "https://")):
        return None
    return Path(url).expanduser()


def _resolve_academy_id(kwargs: dict[str, Any]) -> dict[str, Any]:
    injected = str(kwargs.get("academy_id") or "").strip()
    if injected:
        return {"ok": True, "academy_id": injected}
    discord_user_id = current_discord_user_id()
    if not discord_user_id:
        return {"ok": False, "message": "디스코드 사용자 정보를 확인하지 못했어. 디스코드에서 다시 요청해줘."}
    binding = get_binding(discord_user_id)
    if binding is None:
        return {"ok": False, "message": "학원 계정 연결이 필요해. `/academy login`으로 먼저 연결해줘."}
    return {"ok": True, "academy_id": binding.academy_id}


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)
