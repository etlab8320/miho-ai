"""Runtime-context diagnostics for conversation request preparation."""

from __future__ import annotations

import logging
from typing import Any, Optional

from agent.model_metadata import MINIMUM_CONTEXT_LENGTH

logger = logging.getLogger(__name__)


def ollama_context_limit_error(agent: Any, request_tokens: int) -> Optional[str]:
    """Return a user-facing error when Ollama is loaded with too little context."""
    if not getattr(agent, "tools", None):
        return None

    runtime_ctx = getattr(agent, "_ollama_num_ctx", None)
    if not isinstance(runtime_ctx, int) or runtime_ctx <= 0:
        return None
    if runtime_ctx >= MINIMUM_CONTEXT_LENGTH:
        return None

    model = getattr(agent, "model", "") or "the selected model"
    base_url = getattr(agent, "base_url", "") or "unknown base URL"
    provider = getattr(agent, "provider", "") or "unknown"
    tool_count = len(getattr(agent, "tools", None) or [])

    logger.warning(
        "Ollama runtime context too small for Miho tool use: "
        "model=%s provider=%s base_url=%s runtime_context=%d "
        "minimum_context=%d estimated_request_tokens=%d tool_count=%d "
        "session=%s",
        model,
        provider,
        base_url,
        runtime_ctx,
        MINIMUM_CONTEXT_LENGTH,
        request_tokens,
        tool_count,
        getattr(agent, "session_id", None) or "none",
    )

    return (
        f"Ollama loaded `{model}` with only {runtime_ctx:,} tokens of runtime "
        f"context, but Miho needs at least {MINIMUM_CONTEXT_LENGTH:,} tokens "
        "for reliable tool use.\n\n"
        "Increase the Ollama context for this model and restart/reload the "
        "model before trying again. A known-good starting point is 65,536 "
        "tokens. In Miho config, set `model.ollama_num_ctx: 65536` "
        "(and `model.context_length: 65536` if you also override the displayed "
        "model context). If you manage the model through an Ollama Modelfile, "
        "set `PARAMETER num_ctx 65536` there instead."
    )
