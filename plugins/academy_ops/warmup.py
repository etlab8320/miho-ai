"""Periodic warm-up for the codex router (intent-classifier) connection.

The codex auxiliary connection goes cold when idle: the first call after a gap
takes ~12s (measured on Windows; Linux cold-starts ~3.4s), which blows the
router timeout and forces a body-agent fallback that misroutes ("체크" ->
attendance, etc.). A light periodic ping keeps the connection hot so calls
finish in ~1.6s.

Safety contract: warm-up must never affect real requests or the gateway. Every
error is swallowed, the call is tiny (``max_tokens=1``), and a fast environment
that doesn't need warming simply pays a negligible periodic ping.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def warm_router_connection() -> bool:
    """Fire one tiny router-model call to keep the codex connection warm.

    Returns ``True`` on success, ``False`` otherwise. Never raises — callers
    rely on this being a fire-and-forget no-op when anything is unavailable.
    """
    try:
        from agent.auxiliary_client import async_call_llm

        from .commentary_config import (
            COMMENTARY_PROVIDER,
            ROUTER_EXTRA_BODY,
            ROUTER_MODEL,
        )

        await async_call_llm(
            task="academy_router_warmup",
            provider=COMMENTARY_PROVIDER,
            model=ROUTER_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            temperature=0,
            max_tokens=1,
            timeout=20,
            extra_body=ROUTER_EXTRA_BODY,
        )
        return True
    except Exception as exc:  # warm-up must never break anything
        logger.debug("router warm-up skipped: %s", exc)
        return False
