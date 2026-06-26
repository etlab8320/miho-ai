"""Matrix sender implementation for send_message."""

from __future__ import annotations

import logging
import os
import re
import time

from .common import _AUDIO_EXTS, _IMAGE_EXTS, _VIDEO_EXTS, _VOICE_EXTS, _error

logger = logging.getLogger(__name__)


async def _send_matrix(token, extra, chat_id, message):
    """Send via Matrix Client-Server API.

    Converts markdown to HTML for rich rendering in Matrix clients.
    Falls back to plain text if the ``markdown`` library is not installed.
    """
    try:
        import aiohttp
    except ImportError:
        return {"error": "aiohttp not installed. Run: pip install aiohttp"}
    try:
        homeserver = (extra.get("homeserver") or os.getenv("MATRIX_HOMESERVER", "")).rstrip("/")
        token = token or os.getenv("MATRIX_ACCESS_TOKEN", "")
        if not homeserver or not token:
            return {"error": "Matrix not configured (MATRIX_HOMESERVER, MATRIX_ACCESS_TOKEN required)"}
        txn_id = f"miho_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
        from urllib.parse import quote
        encoded_room = quote(chat_id, safe="")
        url = f"{homeserver}/_matrix/client/v3/rooms/{encoded_room}/send/m.room.message/{txn_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Build message payload with optional HTML formatted_body.
        payload = {"msgtype": "m.text", "body": message}
        try:
            import markdown as _md
            html = _md.markdown(message, extensions=["fenced_code", "tables"])
            # Convert h1-h6 to bold for Element X compatibility.
            html = re.sub(r"<h[1-6]>(.*?)</h[1-6]>", r"<strong>\1</strong>", html)
            payload["format"] = "org.matrix.custom.html"
            payload["formatted_body"] = html
        except ImportError:
            pass

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.put(url, headers=headers, json=payload) as resp:
                if resp.status not in {200, 201}:
                    body = await resp.text()
                    return _error(f"Matrix API error ({resp.status}): {body}")
                data = await resp.json()
        return {"success": True, "platform": "matrix", "chat_id": chat_id, "message_id": data.get("event_id")}
    except Exception as e:
        return _error(f"Matrix send failed: {e}")


async def _send_matrix_via_adapter(pconfig, chat_id, message, media_files=None, thread_id=None):
    """Send via the Matrix adapter so native Matrix media uploads are preserved."""
    try:
        from gateway.platforms.matrix import MatrixAdapter
    except ImportError:
        return {"error": "Matrix dependencies not installed. Run: pip install 'mautrix[encryption]'"}

    media_files = media_files or []

    try:
        adapter = MatrixAdapter(pconfig)
        connected = await adapter.connect()
        if not connected:
            return _error("Matrix connect failed")

        metadata = {"thread_id": thread_id} if thread_id else None
        last_result = None

        if message.strip():
            last_result = await adapter.send(chat_id, message, metadata=metadata)
            if not last_result.success:
                return _error(f"Matrix send failed: {last_result.error}")

        for media_path, is_voice in media_files:
            if not os.path.exists(media_path):
                return _error(f"Media file not found: {media_path}")

            ext = os.path.splitext(media_path)[1].lower()
            if ext in _IMAGE_EXTS:
                last_result = await adapter.send_image_file(chat_id, media_path, metadata=metadata)
            elif ext in _VIDEO_EXTS:
                last_result = await adapter.send_video(chat_id, media_path, metadata=metadata)
            elif ext in _VOICE_EXTS and is_voice:
                last_result = await adapter.send_voice(chat_id, media_path, metadata=metadata)
            elif ext in _AUDIO_EXTS:
                last_result = await adapter.send_voice(chat_id, media_path, metadata=metadata)
            else:
                last_result = await adapter.send_document(chat_id, media_path, metadata=metadata)

            if not last_result.success:
                return _error(f"Matrix media send failed: {last_result.error}")

        if last_result is None:
            return {"error": "No deliverable text or media remained after processing MEDIA tags"}

        return {
            "success": True,
            "platform": "matrix",
            "chat_id": chat_id,
            "message_id": last_result.message_id,
        }
    except Exception as e:
        return _error(f"Matrix send failed: {e}")
    finally:
        try:
            await adapter.disconnect()
        except Exception:
            pass
