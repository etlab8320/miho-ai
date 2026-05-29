"""Promote generated media tool results into gateway-deliverable directives."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable


_TOOL_MEDIA_RE = re.compile(
    r"MEDIA:((?:/|~/)\S+\.(?:png|jpe?g|gif|webp|"
    r"mp4|mov|avi|mkv|webm|ogg|opus|mp3|wav|m4a|"
    r"flac|epub|pdf|zip|rar|7z|docx?|xlsx?|pptx?|"
    r"txt|csv|apk|ipa))",
    re.IGNORECASE,
)


def append_missing_generated_media_directives(
    final_response: str,
    messages: Iterable[dict[str, Any]],
    *,
    history_media_paths: Iterable[str] = (),
) -> str:
    """Append hidden media directives found in tool results when missing.

    The platform adapters already know how to strip and deliver ``MEDIA:``
    paths and markdown image URLs. This function only bridges tool results
    whose media reference never made it into the model's final answer.
    """
    if not final_response:
        return final_response

    directives = _collect_missing_media_directives(
        messages,
        final_response=final_response,
        history_media_paths=set(history_media_paths or ()),
    )
    if not directives:
        return final_response
    return final_response + "\n" + "\n".join(directives)


def _collect_missing_media_directives(
    messages: Iterable[dict[str, Any]],
    *,
    final_response: str,
    history_media_paths: set[str],
) -> list[str]:
    directives: list[str] = []
    has_voice_directive = False

    for msg in messages or []:
        if not isinstance(msg, dict) or msg.get("role") not in {"tool", "function"}:
            continue
        content = str(msg.get("content") or "")
        if not content:
            continue

        for media_path in _media_paths_from_tool_content(content):
            if media_path and media_path not in history_media_paths:
                directives.append(f"MEDIA:{media_path}")
        if "[[audio_as_voice]]" in content:
            has_voice_directive = True

        if _is_image_generate_result(msg, content):
            image_ref = _image_ref_from_json(content)
            directive = _image_ref_to_directive(image_ref, final_response)
            if directive:
                directives.append(directive)

    unique = _dedupe_preserving_order(directives)
    if has_voice_directive and any(item.startswith("MEDIA:") for item in unique):
        unique.insert(0, "[[audio_as_voice]]")
    return unique


def _media_paths_from_tool_content(content: str) -> list[str]:
    paths: list[str] = []
    for match in _TOOL_MEDIA_RE.finditer(content):
        path = match.group(1).strip().rstrip('",}')
        if path:
            paths.append(path)
    return paths


def _is_image_generate_result(msg: dict[str, Any], content: str) -> bool:
    if msg.get("tool_name") == "image_generate":
        return True
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("success") is True
        and isinstance(payload.get("image"), str)
        and payload.get("image")
    )


def _image_ref_from_json(content: str) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return ""
    image = payload.get("image")
    return image.strip() if isinstance(image, str) else ""


def _image_ref_to_directive(image_ref: str, final_response: str) -> str:
    if not image_ref or image_ref in final_response:
        return ""
    lowered = image_ref.lower()
    if lowered.startswith(("http://", "https://")):
        return f"![generated image]({image_ref})"
    if image_ref.startswith(("/", "~/")):
        return f"MEDIA:{image_ref}"
    return ""


def _dedupe_preserving_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique
