"""Promote generated media tool results into gateway-deliverable directives."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

from miho_constants import get_miho_dir
from gateway.attachment_extensions import ATTACHMENT_EXTENSION_PATTERN
from gateway.media_cache_manager import managed_media_dir
from gateway.media_directive_dedupe import (
    dedupe_existing_media_directives,
    dedupe_media_directives,
)


_TOOL_MEDIA_RE = re.compile(
    (
        r'''MEDIA:\s*(?P<path>`(?:/|~/)[^`\n]+?\.(?:{ext})`|'''
        r'''"(?:/|~/)[^"\n]+?\.(?:{ext})"|'''
        r"""'(?:/|~/)[^'\n]+?\.(?:{ext})'|"""
        r'''(?:/|~/)\S+\.(?:{ext}))'''
    ).format(ext=ATTACHMENT_EXTENSION_PATTERN),
    re.IGNORECASE,
)
_TOOL_LOCAL_MEDIA_RE = re.compile(
    r"(?P<path>(?:/|~/)\S+\.(?:{ext}))".format(ext=ATTACHMENT_EXTENSION_PATTERN),
    re.IGNORECASE,
)
_TOOL_LOCAL_MEDIA_SAFE_PARTS = (
    "/.miho/cache/media/",
    "/.miho/discord_exports/",
    # Skills that render their own PNG (e.g. the health report card via a
    # headless-Chrome screenshot) save under media_cache/. The model is told to
    # attach it with a MEDIA: line, but when it forgets, this lets the safety net
    # promote a structured path the skill exposed so the image still ships turn 1.
    "/.miho/media_cache/",
)
_MEDIA_CACHE_ROOT = get_miho_dir("cache/media", "media_cache")
_MEDIA_CACHE_DIR: Path | None = None
_RAW_MEDIA_TOOL_NAMES = {"tts", "text_to_speech", "text_to_speech_tool"}
_MEDIA_TAG_KEYS = {"media_tag"}
_MEDIA_PATH_KEYS = {"image_path", "file_path", "audio_path", "video_path", "document_path", "path"}


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

    final_response = dedupe_existing_media_directives(final_response, media_re=_TOOL_MEDIA_RE)
    directives = _collect_missing_media_directives(
        messages,
        final_response=final_response,
        history_media_paths=set(history_media_paths or ()),
    )
    if not directives:
        return final_response
    clean_response = _strip_dangling_attachment_label(final_response)
    combined_response = clean_response + "\n" + "\n".join(directives)
    return dedupe_existing_media_directives(combined_response, media_re=_TOOL_MEDIA_RE)


def _collect_missing_media_directives(
    messages: Iterable[dict[str, Any]],
    *,
    final_response: str,
    history_media_paths: set[str],
) -> list[str]:
    directives: list[str] = []
    known_media_paths = _response_media_paths(final_response)
    has_voice_directive = False

    for msg in _current_turn_messages(messages):
        if not isinstance(msg, dict) or msg.get("role") not in {"tool", "function"}:
            continue
        content = str(msg.get("content") or "")
        if not content:
            continue

        structured_directives = _structured_media_directives_from_tool_content(
            content,
            known_media_paths=known_media_paths,
        )
        directives.extend(
            directive
            for directive in structured_directives
            if not _directive_matches_history(directive, history_media_paths)
        )
        if _should_scan_raw_tool_media(msg):
            for media_path in _media_paths_from_tool_content(content):
                if media_path and media_path not in history_media_paths:
                    directives.append(f"MEDIA:{media_path}")
            for media_path in _local_media_paths_from_tool_content(content):
                if media_path and media_path not in history_media_paths:
                    directives.append(f"MEDIA:{media_path}")
        if "[[audio_as_voice]]" in content and (structured_directives or _should_scan_raw_tool_media(msg)):
            has_voice_directive = True

        if _is_image_generate_result(msg, content):
            image_ref = _image_ref_from_json(content)
            directive = _image_ref_to_directive(image_ref, final_response)
            if directive:
                directives.append(directive)

    unique = dedupe_media_directives(
        directives,
        known_media_paths=known_media_paths,
        path_matches_any=_path_matches_any,
    )
    if has_voice_directive and any(item.startswith("MEDIA:") for item in unique):
        unique.insert(0, "[[audio_as_voice]]")
    return unique


def _current_turn_messages(messages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    message_list = [msg for msg in messages or [] if isinstance(msg, dict)]
    last_user_index = -1
    for index, msg in enumerate(message_list):
        if msg.get("role") == "user":
            last_user_index = index
    if last_user_index < 0:
        return message_list
    return message_list[last_user_index + 1 :]


def _strip_dangling_attachment_label(text: str) -> str:
    return re.sub(r"(?:\n\s*)+(?:첨부|이미지)\s*:\s*$", "", text).rstrip()


def _structured_media_directives_from_tool_content(
    content: str,
    *,
    known_media_paths: set[str],
) -> list[str]:
    payload = _json_payload(content)
    if not isinstance(payload, dict):
        return []
    directives: list[str] = []
    seen_paths = set(known_media_paths)
    for key in _MEDIA_TAG_KEYS:
        value = payload.get(key)
        if isinstance(value, str):
            for directive in _media_tag_directives(value):
                path = _media_path_from_directive(directive)
                if path and _path_matches_any(path, seen_paths):
                    continue
                directives.append(directive)
                if path:
                    seen_paths.add(path)
    for key in _MEDIA_PATH_KEYS:
        value = payload.get(key)
        if isinstance(value, str):
            directive = _safe_local_path_directive(value, seen_paths)
            if directive:
                directives.append(directive)
                path = _media_path_from_directive(directive)
                if path:
                    seen_paths.add(path)
    return directives


def _json_payload(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _media_tag_directives(value: str) -> list[str]:
    directives: list[str] = []
    if "[[audio_as_voice]]" in value:
        directives.append("[[audio_as_voice]]")
    for media_path in _media_paths_from_tool_content(value):
        directives.append(f"MEDIA:{media_path}")
    return directives


def _safe_local_path_directive(value: str, known_media_paths: set[str] | None = None) -> str:
    path = _clean_path(value)
    if known_media_paths and _path_matches_any(path, known_media_paths):
        return ""
    if not _is_safe_generated_media_path(path):
        return ""
    delivery_path = _delivery_path_for_generated_media(path)
    return f"MEDIA:{delivery_path}" if delivery_path else ""


def _should_scan_raw_tool_media(msg: dict[str, Any]) -> bool:
    return str(msg.get("tool_name") or msg.get("name") or "").strip() in _RAW_MEDIA_TOOL_NAMES


def _directive_matches_history(directive: str, history_media_paths: set[str]) -> bool:
    if not directive.startswith("MEDIA:"):
        return False
    return directive.removeprefix("MEDIA:") in history_media_paths


def _response_media_paths(response: str) -> set[str]:
    paths = {_clean_path(path) for path in _media_paths_from_tool_content(response)}
    paths.update(_local_media_paths_without_promotion(response))
    return {path for path in paths if path}


def _local_media_paths_without_promotion(content: str) -> set[str]:
    paths: set[str] = set()
    for match in _TOOL_LOCAL_MEDIA_RE.finditer(content):
        path = _clean_path(match.group("path"))
        if _is_safe_generated_media_path(path):
            paths.add(path)
    return paths


def _media_path_from_directive(directive: str) -> str:
    if not directive.startswith("MEDIA:"):
        return ""
    return _clean_path(directive.removeprefix("MEDIA:"))


def _path_matches_any(path: str, candidates: set[str]) -> bool:
    clean = _clean_path(path)
    if not clean:
        return False
    candidate_paths = {clean}
    promoted = _promoted_equivalent_path(clean)
    if promoted:
        candidate_paths.add(promoted)
    if candidate_paths & candidates:
        return True
    try:
        resolved = Path(clean).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return False
    for candidate in candidates:
        try:
            if resolved == Path(candidate).resolve(strict=True):
                return True
        except (OSError, RuntimeError, ValueError):
            continue
    return False


def _promoted_equivalent_path(path: str) -> str:
    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return ""
    normalized = str(resolved)
    if "/.miho/cache/media/" in normalized:
        return str(resolved)
    if not _is_safe_generated_media_path(str(resolved)):
        return ""
    return str(_gateway_promoted_dir() / resolved.name)


def _media_paths_from_tool_content(content: str) -> list[str]:
    paths: list[str] = []
    for match in _TOOL_MEDIA_RE.finditer(content):
        path = _clean_path(match.group("path"))
        if path:
            paths.append(path)
    return paths


def _local_media_paths_from_tool_content(content: str) -> list[str]:
    paths: list[str] = []
    for match in _TOOL_LOCAL_MEDIA_RE.finditer(content):
        path = _clean_path(match.group("path"))
        if _is_safe_generated_media_path(path):
            promoted = _delivery_path_for_generated_media(path)
            if promoted:
                paths.append(promoted)
    return paths


def _clean_path(path: str) -> str:
    clean = path.strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in "`\"'":
        clean = clean[1:-1].strip()
    return os.path.expanduser(clean.rstrip('",}.)]'))


def _is_safe_generated_media_path(path: str) -> bool:
    if not path:
        return False
    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return False
    normalized = str(resolved)
    return resolved.is_file() and any(part in normalized for part in _TOOL_LOCAL_MEDIA_SAFE_PARTS)


def _delivery_path_for_generated_media(path: str) -> str:
    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return ""
    normalized = str(resolved)
    if "/.miho/cache/media/" in normalized:
        return str(resolved)
    try:
        target_dir = _gateway_promoted_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / resolved.name
        shutil.copy2(resolved, target)
    except OSError:
        return ""
    return str(target)


def _gateway_promoted_dir() -> Path:
    if _MEDIA_CACHE_DIR is not None:
        return Path(_MEDIA_CACHE_DIR)
    return managed_media_dir("gateway_promoted", root=_MEDIA_CACHE_ROOT)


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
