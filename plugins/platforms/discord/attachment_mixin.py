from __future__ import annotations

import sys

from .mixin_deps import *
from .voice_receiver import VoiceReceiver


def _adapter_global(name: str, fallback):
    adapter_module = sys.modules.get("plugins.platforms.discord.adapter")
    return getattr(adapter_module, name, fallback)



class DiscordAttachmentMixin:

    async def _read_attachment_bytes(self, att) -> Optional[bytes]:
        """Read an attachment via discord.py's authenticated bot session.

        Returns the raw bytes on success, or ``None`` if ``att`` doesn't
        expose a callable ``read()`` or the read itself fails. Callers
        should treat ``None`` as a signal to fall back to the URL-based
        downloaders.
        """
        reader = getattr(att, "read", None)
        if reader is None or not callable(reader):
            return None
        try:
            return await reader()
        except Exception as e:
            logger.warning(
                "[Discord] Authenticated attachment read failed for %s: %s",
                getattr(att, "filename", None) or getattr(att, "url", "<unknown>"),
                e,
            )
            return None


    async def _cache_discord_image(self, att, ext: str) -> str:
        """Cache a Discord image attachment to local disk.

        Primary path: ``att.read()`` + ``cache_image_from_bytes``
        (authenticated, no SSRF gate).

        Fallback: ``cache_image_from_url`` (plain httpx, SSRF-gated).
        """
        raw_bytes = await self._read_attachment_bytes(att)
        if raw_bytes is not None:
            try:
                cache_bytes = _adapter_global(
                    "cache_image_from_bytes", cache_image_from_bytes
                )
                return cache_bytes(raw_bytes, ext=ext)
            except Exception as e:
                logger.debug(
                    "[Discord] cache_image_from_bytes rejected att.read() data; falling back to URL: %s",
                    e,
                )
        cache_url = _adapter_global("cache_image_from_url", cache_image_from_url)
        return await cache_url(att.url, ext=ext)


    async def _cache_discord_audio(self, att, ext: str) -> str:
        """Cache a Discord audio attachment to local disk.

        Primary path: ``att.read()`` + ``cache_audio_from_bytes``
        (authenticated, no SSRF gate).

        Fallback: ``cache_audio_from_url`` (plain httpx, SSRF-gated).
        """
        raw_bytes = await self._read_attachment_bytes(att)
        if raw_bytes is not None:
            try:
                cache_bytes = _adapter_global(
                    "cache_audio_from_bytes", cache_audio_from_bytes
                )
                return cache_bytes(raw_bytes, ext=ext)
            except Exception as e:
                logger.debug(
                    "[Discord] cache_audio_from_bytes failed; falling back to URL: %s",
                    e,
                )
        cache_url = _adapter_global("cache_audio_from_url", cache_audio_from_url)
        return await cache_url(att.url, ext=ext)


    async def _cache_discord_document(self, att, ext: str) -> bytes:
        """Download a Discord document attachment and return the raw bytes.

        Primary path: ``att.read()`` (authenticated, no SSRF gate).

        Fallback: SSRF-gated ``aiohttp`` download. This closes the gap
        where the old document path made raw ``aiohttp.ClientSession``
        requests with no safety check (#11345). The caller is responsible
        for passing the returned bytes to ``cache_document_from_bytes``
        (and, where applicable, for injecting text content).
        """
        raw_bytes = await self._read_attachment_bytes(att)
        if raw_bytes is not None:
            return raw_bytes

        # Fallback: SSRF-gated URL download.
        safe_url = _adapter_global("is_safe_url", is_safe_url)
        if not safe_url(att.url):
            raise ValueError(
                f"Blocked unsafe attachment URL (SSRF protection): {att.url}"
            )
        import aiohttp
        from gateway.platforms.base import resolve_proxy_url, proxy_kwargs_for_aiohttp
        _proxy = resolve_proxy_url(platform_env_var="DISCORD_PROXY")
        _sess_kw, _req_kw = proxy_kwargs_for_aiohttp(_proxy)
        async with aiohttp.ClientSession(**_sess_kw) as session:
            async with session.get(
                att.url,
                timeout=aiohttp.ClientTimeout(total=30),
                **_req_kw,
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                return await resp.read()
