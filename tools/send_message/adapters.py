"""Live gateway adapter send helpers for send_message."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .common import _IMAGE_EXTS, _VIDEO_EXTS

logger = logging.getLogger(__name__)


async def _send_via_adapter(
    platform,
    pconfig,
    chat_id,
    chunk,
    *,
    thread_id=None,
    media_files=None,
    force_document=False,
):
    """Send a message via a live gateway adapter, with a standalone fallback
    for out-of-process callers (e.g. cron running separately from the gateway).

    Order of attempts:
      1. Live in-process adapter via ``_gateway_runner_ref()`` (the path that
         existed before this change).
      2. The plugin's ``standalone_sender_fn`` registered on its
         ``PlatformEntry`` (used when the gateway is not in this process, so
         the runner weakref is ``None``).
      3. A descriptive error explaining both options.
    """
    runner = None
    try:
        from gateway.run import _gateway_runner_ref
        runner = _gateway_runner_ref()
    except Exception:
        runner = None

    if runner is not None:
        try:
            adapter = runner.adapters.get(platform)
        except Exception:
            adapter = None
        if adapter is not None:
            try:
                metadata = {"thread_id": thread_id} if thread_id else None
                result = await _send_live_adapter_payload(
                    adapter,
                    chat_id=chat_id,
                    content=chunk,
                    metadata=metadata,
                    media_files=media_files,
                    force_document=force_document,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                return {"error": f"Plugin platform send failed: {e}"}
            if result.get("success"):
                return result
            return {"error": f"Adapter send failed: {result.get('error')}"}

    platform_name = platform.value if hasattr(platform, "value") else str(platform)
    entry = None
    try:
        from gateway.platform_registry import platform_registry
        entry = platform_registry.get(platform_name)
    except Exception:
        entry = None

    if entry is not None and entry.standalone_sender_fn is not None:
        try:
            result = await entry.standalone_sender_fn(
                pconfig,
                chat_id,
                chunk,
                thread_id=thread_id,
                media_files=media_files,
                force_document=force_document,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("Plugin standalone send for %s raised", platform_name, exc_info=True)
            return {"error": f"Plugin standalone send failed: {e}"}

        if isinstance(result, dict) and (result.get("success") or result.get("error")):
            return result
        return {
            "error": (
                f"Plugin standalone send for '{platform_name}' returned an "
                f"invalid result: expected a dict with 'success' or 'error' "
                f"keys, got {type(result).__name__}"
            )
        }

    return {
        "error": (
            f"No live adapter for platform '{platform_name}'. Is the gateway "
            f"running with this platform connected? For out-of-process delivery "
            f"(e.g. cron in a separate process), the platform plugin must "
            f"register a standalone_sender_fn on its PlatformEntry."
        )
    }


async def _send_live_adapter_payload(
    adapter,
    *,
    chat_id: str,
    content: str,
    metadata,
    media_files=None,
    force_document: bool = False,
) -> dict:
    last_payload: dict | None = None
    media_items = list(media_files or [])
    if content.strip() and not media_items:
        text_result = await adapter.send(chat_id=chat_id, content=content, metadata=metadata)
        last_payload = _adapter_send_result_payload(text_result)
        if not last_payload.get("success"):
            return last_payload

    caption = content.strip() or None
    for index, (media_path, is_voice) in enumerate(media_items):
        media_result = await _send_live_adapter_media(
            adapter,
            chat_id=chat_id,
            media_path=str(media_path),
            is_voice=bool(is_voice),
            metadata=metadata,
            force_document=force_document,
            caption=caption if index == 0 else None,
        )
        last_payload = _adapter_send_result_payload(media_result)
        if not last_payload.get("success"):
            return last_payload

    return last_payload or {"success": True, "message_id": None}


async def _send_live_adapter_media(
    adapter,
    *,
    chat_id: str,
    media_path: str,
    is_voice: bool,
    metadata,
    force_document: bool,
    caption: str | None = None,
):
    from gateway.platforms.base import should_send_media_as_audio

    ext = Path(media_path).suffix.lower()
    platform = getattr(adapter, "platform", getattr(adapter, "_platform", None))
    if should_send_media_as_audio(platform, ext, is_voice=is_voice):
        return await adapter.send_voice(
            chat_id=chat_id,
            audio_path=media_path,
            caption=caption,
            metadata=metadata,
        )
    if ext in _VIDEO_EXTS:
        return await adapter.send_video(
            chat_id=chat_id,
            video_path=media_path,
            caption=caption,
            metadata=metadata,
        )
    if ext in _IMAGE_EXTS and not force_document:
        return await adapter.send_image_file(
            chat_id=chat_id,
            image_path=media_path,
            caption=caption,
            metadata=metadata,
        )
    return await adapter.send_document(
        chat_id=chat_id,
        file_path=media_path,
        caption=caption,
        metadata=metadata,
    )


def _adapter_send_result_payload(result) -> dict:
    if isinstance(result, dict):
        return result
    if bool(getattr(result, "success", False)):
        return {"success": True, "message_id": getattr(result, "message_id", None)}
    return {"error": getattr(result, "error", None) or "live adapter send failed"}
