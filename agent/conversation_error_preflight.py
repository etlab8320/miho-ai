"""Early API-error recovery before structured retry handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from agent.message_sanitization import (
    _sanitize_messages_non_ascii,
    _sanitize_messages_surrogates,
    _sanitize_structure_non_ascii,
    _sanitize_structure_surrogates,
    _sanitize_tools_non_ascii,
    _strip_images_from_messages,
    _strip_non_ascii,
)

IMAGE_REJECTION_PHRASES = (
    "only 'text' content type is supported",
    "only text content type is supported",
    "image_url is not supported",
    "image content is not supported",
    "multimodal is not supported",
    "multimodal content is not supported",
    "multimodal input is not supported",
    "vision is not supported",
    "vision input is not supported",
    "does not support images",
    "does not support image input",
    "does not support multimodal",
    "does not support vision",
    "model does not support image",
    "image_url'. expected",
    "unknown variant `image_url`, expected `text`",
    "unknown variant image_url, expected text",
)


@dataclass(frozen=True)
class ErrorPreflightResult:
    action: str
    active_system_prompt: str | None


def handle_early_api_error_recovery(
    *,
    agent: Any,
    api_error: Exception,
    messages: List[Dict[str, Any]],
    api_messages: List[Dict[str, Any]],
    api_kwargs: Dict[str, Any] | None,
    active_system_prompt: str | None,
) -> ErrorPreflightResult:
    """Handle recovery paths that do not need structured error classification."""

    unicode_result = _handle_unicode_recovery(
        agent=agent,
        api_error=api_error,
        messages=messages,
        api_messages=api_messages,
        api_kwargs=api_kwargs,
        active_system_prompt=active_system_prompt,
    )
    if unicode_result.action == "continue":
        return unicode_result

    if _handle_image_rejection(agent=agent, api_error=api_error, messages=messages, api_messages=api_messages):
        return ErrorPreflightResult("continue", unicode_result.active_system_prompt)

    return ErrorPreflightResult("proceed", unicode_result.active_system_prompt)


def _handle_unicode_recovery(
    *,
    agent: Any,
    api_error: Exception,
    messages: List[Dict[str, Any]],
    api_messages: List[Dict[str, Any]],
    api_kwargs: Dict[str, Any] | None,
    active_system_prompt: str | None,
) -> ErrorPreflightResult:
    if not (
        isinstance(api_error, UnicodeEncodeError)
        and getattr(agent, "_unicode_sanitization_passes", 0) < 2
    ):
        return ErrorPreflightResult("proceed", active_system_prompt)

    err = str(api_error).lower()
    is_ascii_codec = "'ascii'" in err or "ascii" in err
    is_surrogate_error = "surrogate" in err or ("'utf-8'" in err and not is_ascii_codec)

    surrogates_found = _sanitize_messages_surrogates(messages)
    if isinstance(api_messages, list) and _sanitize_messages_surrogates(api_messages):
        surrogates_found = True
    if isinstance(api_kwargs, dict) and _sanitize_structure_surrogates(api_kwargs):
        surrogates_found = True
    if isinstance(getattr(agent, "prefill_messages", None), list):
        if _sanitize_messages_surrogates(agent.prefill_messages):
            surrogates_found = True

    if surrogates_found or is_surrogate_error:
        agent._unicode_sanitization_passes += 1
        if surrogates_found:
            agent._vprint(
                f"{agent.log_prefix}⚠️  Stripped invalid surrogate characters from messages. Retrying...",
                force=True,
            )
        else:
            agent._vprint(
                f"{agent.log_prefix}⚠️  Surrogate encoding error — retrying after full-payload sanitization...",
                force=True,
            )
        return ErrorPreflightResult("continue", active_system_prompt)

    if is_ascii_codec:
        active_system_prompt = _sanitize_ascii_payload(agent, messages, api_messages, api_kwargs, active_system_prompt)
        return ErrorPreflightResult("continue", active_system_prompt)

    return ErrorPreflightResult("proceed", active_system_prompt)


def _sanitize_ascii_payload(
    agent: Any,
    messages: List[Dict[str, Any]],
    api_messages: List[Dict[str, Any]],
    api_kwargs: Dict[str, Any] | None,
    active_system_prompt: str | None,
) -> str | None:
    agent._force_ascii_payload = True
    messages_sanitized = _sanitize_messages_non_ascii(messages)
    if isinstance(api_messages, list):
        _sanitize_messages_non_ascii(api_messages)
    if isinstance(api_kwargs, dict):
        _sanitize_structure_non_ascii(api_kwargs)

    prefill_sanitized = False
    if isinstance(getattr(agent, "prefill_messages", None), list):
        prefill_sanitized = _sanitize_messages_non_ascii(agent.prefill_messages)

    tools_sanitized = False
    if isinstance(getattr(agent, "tools", None), list):
        tools_sanitized = _sanitize_tools_non_ascii(agent.tools)

    system_sanitized = False
    if isinstance(active_system_prompt, str):
        clean_system = _strip_non_ascii(active_system_prompt)
        if clean_system != active_system_prompt:
            active_system_prompt = clean_system
            agent._cached_system_prompt = clean_system
            system_sanitized = True
    if isinstance(getattr(agent, "ephemeral_system_prompt", None), str):
        clean_ephemeral = _strip_non_ascii(agent.ephemeral_system_prompt)
        if clean_ephemeral != agent.ephemeral_system_prompt:
            agent.ephemeral_system_prompt = clean_ephemeral
            system_sanitized = True

    headers_sanitized = False
    default_headers = (
        agent._client_kwargs.get("default_headers")
        if isinstance(getattr(agent, "_client_kwargs", None), dict)
        else None
    )
    if isinstance(default_headers, dict):
        headers_sanitized = _sanitize_structure_non_ascii(default_headers)

    credential_sanitized = _sanitize_api_key(agent)
    agent._unicode_sanitization_passes += 1
    if (
        messages_sanitized
        or prefill_sanitized
        or tools_sanitized
        or system_sanitized
        or headers_sanitized
        or credential_sanitized
    ):
        agent._vprint(
            f"{agent.log_prefix}⚠️  System encoding is ASCII — stripped non-ASCII characters from request payload. Retrying...",
            force=True,
        )
    else:
        agent._vprint(
            f"{agent.log_prefix}⚠️  System encoding is ASCII — enabling full-payload sanitization for retry...",
            force=True,
        )
    return active_system_prompt


def _sanitize_api_key(agent: Any) -> bool:
    raw_key = getattr(agent, "api_key", None) or ""
    if not (raw_key and isinstance(raw_key, str)):
        return False
    clean_key = _strip_non_ascii(raw_key)
    if clean_key == raw_key:
        return False
    agent.api_key = clean_key
    if isinstance(getattr(agent, "_client_kwargs", None), dict):
        agent._client_kwargs["api_key"] = clean_key
    if getattr(agent, "client", None) is not None and hasattr(agent.client, "api_key"):
        agent.client.api_key = clean_key
    agent._vprint(
        f"{agent.log_prefix}⚠️  API key contained non-ASCII characters "
        "(bad copy-paste?) — stripped them. If auth fails, "
        "re-copy the key from your provider's dashboard.",
        force=True,
    )
    return True


def _handle_image_rejection(
    *,
    agent: Any,
    api_error: Exception,
    messages: List[Dict[str, Any]],
    api_messages: List[Dict[str, Any]],
) -> bool:
    err_body = ""
    try:
        err_body = str(
            getattr(api_error, "body", None)
            or getattr(api_error, "message", None)
            or str(api_error)
        )
    except Exception:
        pass
    status = getattr(api_error, "status_code", None)
    status_ok = status is None or (400 <= int(status) < 500)
    looks_like_image_rejection = any(
        phrase in err_body.lower() for phrase in IMAGE_REJECTION_PHRASES
    )
    if not (
        getattr(agent, "_vision_supported", True)
        and looks_like_image_rejection
        and status_ok
    ):
        return False
    agent._vision_supported = False
    images_removed = _strip_images_from_messages(messages)
    if isinstance(api_messages, list):
        _strip_images_from_messages(api_messages)
    agent._vprint(
        f"{agent.log_prefix}⚠️  Server rejected image content — "
        "switching to text-only mode for this session"
        + (". Stripped images from history and retrying." if images_removed else "."),
        force=True,
    )
    return True
