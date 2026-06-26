"""Signal sender implementation for send_message."""

from __future__ import annotations

import logging
import os
import time

from .common import _error

logger = logging.getLogger(__name__)


async def _send_signal(extra, chat_id, message, media_files=None):
    """Send via signal-cli JSON-RPC API.

    Supports both text-only and text-with-attachments (images/audio/documents).
    Multi-attachment sends are chunked into batches of
    SIGNAL_MAX_ATTACHMENTS_PER_MSG and metered by the process-wide
    SignalAttachmentScheduler — same bucket the gateway adapter uses, so
    sends from this tool and inbound-driven replies share rate-limit state.
    """
    try:
        import httpx
    except ImportError:
        return {"error": "httpx not installed"}

    from gateway.platforms.signal_rate_limit import (
        SIGNAL_BATCH_PACING_NOTICE_THRESHOLD,
        SIGNAL_MAX_ATTACHMENTS_PER_MSG,
        SIGNAL_RATE_LIMIT_MAX_ATTEMPTS,
        _extract_retry_after_seconds,
        _format_wait,
        _is_signal_rate_limit_error,
        _signal_send_timeout,
        get_scheduler,
    )

    try:
        http_url = extra.get("http_url", "http://127.0.0.1:8080").rstrip("/")
        account = extra.get("account", "")
        if not account:
            return {"error": "Signal account not configured"}

        valid_media = media_files or []
        attachment_paths = []
        for media_path, _is_voice in valid_media:
            if os.path.exists(media_path):
                attachment_paths.append(media_path)
            else:
                logger.warning("Signal media file not found, skipping: %s", media_path)

        # Chunk attachments. With no attachments we still emit one batch
        # (text only). With attachments, the text rides on batch #0 so the
        # caption isn't repeated across every chunk.
        if attachment_paths:
            att_batches = [
                attachment_paths[i:i + SIGNAL_MAX_ATTACHMENTS_PER_MSG]
                for i in range(0, len(attachment_paths), SIGNAL_MAX_ATTACHMENTS_PER_MSG)
            ]
        else:
            att_batches = [[]]

        async def _post(batch_attachments, batch_message):
            params = {"account": account, "message": batch_message}
            if chat_id.startswith("group:"):
                params["groupId"] = chat_id[6:]
            else:
                params["recipient"] = [chat_id]
            if batch_attachments:
                params["attachments"] = batch_attachments

            payload = {
                "jsonrpc": "2.0",
                "method": "send",
                "params": params,
                "id": f"send_{int(time.time() * 1000)}",
            }
            timeout = _signal_send_timeout(len(batch_attachments) if batch_attachments else 0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{http_url}/api/v1/rpc", json=payload)
                resp.raise_for_status()
                return resp.json()

        async def _send_inline_notice(text: str) -> None:
            """Best-effort one-shot RPC for a user-facing pacing notice."""
            notice_params = {"account": account, "message": text}
            if chat_id.startswith("group:"):
                notice_params["groupId"] = chat_id[6:]
            else:
                notice_params["recipient"] = [chat_id]
            try:
                async with httpx.AsyncClient(timeout=30.0) as _client:
                    await _client.post(
                        f"{http_url}/api/v1/rpc",
                        json={
                            "jsonrpc": "2.0",
                            "method": "send",
                            "params": notice_params,
                            "id": f"notice_{int(time.time() * 1000)}",
                        },
                    )
            except Exception as _e:
                logger.warning("Signal: inline notice failed: %s", _e)

        scheduler = get_scheduler()
        logger.info(
            "send_message Signal: scheduler state=%s, %d attachment(s) in %d batch(es)",
            scheduler.state(), len(attachment_paths), len(att_batches),
        )
        failed_batches: list[int] = []
        for idx, att_batch in enumerate(att_batches):
            n = len(att_batch)
            if n > 0:
                estimated = scheduler.estimate_wait(n)
                if estimated >= SIGNAL_BATCH_PACING_NOTICE_THRESHOLD:
                    await _send_inline_notice(
                        f"(More images coming — pausing ~{_format_wait(estimated)} "
                        f"for Signal rate limit, batch {idx + 1}/{len(att_batches)}.)"
                    )

            batch_message = message if idx == 0 else ""

            for attempt in range(1, SIGNAL_RATE_LIMIT_MAX_ATTEMPTS + 1):
                try:
                    await scheduler.acquire(n)
                    _rpc_t0 = time.monotonic()
                    data = await _post(att_batch, batch_message)
                    _rpc_duration = time.monotonic() - _rpc_t0
                    if "error" not in data:
                        await scheduler.report_rpc_duration(_rpc_duration, n)
                        break

                    err = data["error"]

                    if not _is_signal_rate_limit_error(err):
                        return _error(f"Signal RPC error on batch {idx + 1}/{len(att_batches)}: {err}")

                    server_retry_after = _extract_retry_after_seconds(err)
                    scheduler.feedback(server_retry_after, n)

                    if attempt >= SIGNAL_RATE_LIMIT_MAX_ATTEMPTS:
                        failed_batches.append(idx + 1)
                        logger.error(
                            "Signal: rate-limit retries exhausted on batch %d/%d "
                            "(%d attachments lost, server retry_after=%s)",
                            idx + 1, len(att_batches), n,
                            f"{server_retry_after:.0f}s" if server_retry_after else "unknown",
                        )
                        break
                    logger.warning(
                        "Signal: rate-limited on batch %d/%d "
                        "(attempt %d/%d, server retry_after=%s); "
                        "scheduler will pace the retry",
                        idx + 1, len(att_batches),
                        attempt, SIGNAL_RATE_LIMIT_MAX_ATTEMPTS,
                        f"{server_retry_after:.0f}s" if server_retry_after else "unknown",
                    )
                except Exception as e:
                    if attempt >= SIGNAL_RATE_LIMIT_MAX_ATTEMPTS:
                        failed_batches.append(idx + 1)
                        logger.error(
                            "Signal: send error on batch %d/%d after %d attempts: %s",
                            idx + 1, len(att_batches), attempt, str(e)
                        )
                        break
                    logger.warning(
                        "Signal: transient error on batch %d/%d (attempt %d/%d): %s; will retry",
                        idx + 1, len(att_batches), attempt, SIGNAL_RATE_LIMIT_MAX_ATTEMPTS, str(e)
                    )

        warnings = []
        if len(attachment_paths) < len(valid_media):
            warnings.append("Some media files were skipped (not found on disk)")
        if failed_batches:
            warnings.append(
                f"Signal rate-limited {len(failed_batches)} batch(es) "
                f"(#{', #'.join(str(b) for b in failed_batches)})"
            )

        if failed_batches and len(failed_batches) == len(att_batches):
            return _error(
                f"Signal: every batch ({len(att_batches)}) hit rate limit; "
                f"no attachments delivered"
            )

        result = {"success": True, "platform": "signal", "chat_id": chat_id}
        if warnings:
            result["warnings"] = warnings
        return result
    except Exception as e:
        return _error(f"Signal send failed: {e}")
