"""Image-too-large retry recovery for conversation requests."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def try_shrink_image_parts_in_messages(api_messages: list) -> bool:
    """Re-encode oversized native image parts at a smaller size."""
    if not api_messages:
        return False

    try:
        from tools.vision_tools import _resize_image_for_vision
    except Exception as exc:
        logger.warning("image-shrink recovery: vision_tools unavailable — %s", exc)
        return False

    target_bytes = 4 * 1024 * 1024
    changed_count = 0

    def _shrink_data_url(url: str) -> Optional[str]:
        if not isinstance(url, str) or not url.startswith("data:"):
            return None
        if len(url) <= target_bytes:
            return None
        try:
            header, _, data = url.partition(",")
            mime = "image/jpeg"
            if header.startswith("data:"):
                mime_part = header[len("data:"):].split(";", 1)[0].strip()
                if mime_part.startswith("image/"):
                    mime = mime_part
            import base64 as b64

            raw = b64.b64decode(data)
            suffix = {
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp",
                "image/jpeg": ".jpg",
                "image/jpg": ".jpg",
                "image/bmp": ".bmp",
            }.get(mime, ".jpg")
            tmp = tempfile.NamedTemporaryFile(
                prefix="miho_shrink_",
                suffix=suffix,
                delete=False,
            )
            try:
                tmp.write(raw)
                tmp.close()
                resized = _resize_image_for_vision(
                    Path(tmp.name),
                    mime_type=mime,
                    max_base64_bytes=target_bytes,
                )
            finally:
                try:
                    Path(tmp.name).unlink(missing_ok=True)
                except Exception:
                    pass
            if not resized or len(resized) >= len(url):
                return None
            return resized
        except Exception as exc:
            logger.warning("image-shrink recovery: re-encode failed — %s", exc)
            return None

    for msg in api_messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") not in {"image_url", "input_image"}:
                continue
            image_value = part.get("image_url")
            if isinstance(image_value, dict):
                resized = _shrink_data_url(image_value.get("url", ""))
                if resized:
                    image_value["url"] = resized
                    changed_count += 1
            elif isinstance(image_value, str):
                resized = _shrink_data_url(image_value)
                if resized:
                    part["image_url"] = resized
                    changed_count += 1

    if changed_count:
        logger.info(
            "image-shrink recovery: re-encoded %d image part(s) to fit under %.0f MB",
            changed_count,
            target_bytes / (1024 * 1024),
        )
    return changed_count > 0
