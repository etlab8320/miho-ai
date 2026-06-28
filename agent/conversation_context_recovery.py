"""Context and payload-size recovery for API errors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from agent.error_classifier import FailoverReason
from agent.model_metadata import (
    get_next_probe_tier,
    parse_available_output_tokens_from_error,
    parse_context_limit_from_error,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextRecoveryResult:
    action: str
    messages: List[Dict[str, Any]]
    active_system_prompt: str | None
    conversation_history: List[Dict[str, Any]] | None
    compression_attempts: int
    is_context_length_error: bool
    restart_with_compressed_messages: bool
    return_value: Dict[str, Any] | None = None


def handle_context_recovery(
    *,
    agent: Any,
    classified: Any,
    status_code: int | None,
    error_msg: str,
    messages: List[Dict[str, Any]],
    active_system_prompt: str | None,
    conversation_history: List[Dict[str, Any]] | None,
    system_message: str | None,
    approx_tokens: int,
    effective_task_id: str,
    api_call_count: int,
    compression_attempts: int,
    max_compression_attempts: int,
    time_module: Any,
) -> ContextRecoveryResult:
    """Handle recoverable context window and payload-size failures."""

    if classified.reason == FailoverReason.long_context_tier:
        return _handle_long_context_tier(
            agent=agent,
            messages=messages,
            active_system_prompt=active_system_prompt,
            conversation_history=conversation_history,
            system_message=system_message,
            approx_tokens=approx_tokens,
            effective_task_id=effective_task_id,
            api_call_count=api_call_count,
            compression_attempts=compression_attempts,
            max_compression_attempts=max_compression_attempts,
            time_module=time_module,
        )

    if classified.reason == FailoverReason.payload_too_large:
        _print_github_413_hint(agent, status_code)
        return _handle_payload_too_large(
            agent=agent,
            messages=messages,
            active_system_prompt=active_system_prompt,
            conversation_history=conversation_history,
            system_message=system_message,
            approx_tokens=approx_tokens,
            effective_task_id=effective_task_id,
            api_call_count=api_call_count,
            compression_attempts=compression_attempts,
            max_compression_attempts=max_compression_attempts,
            time_module=time_module,
        )

    is_context_length_error = classified.reason == FailoverReason.context_overflow
    if is_context_length_error:
        return _handle_context_overflow(
            agent=agent,
            error_msg=error_msg,
            messages=messages,
            active_system_prompt=active_system_prompt,
            conversation_history=conversation_history,
            system_message=system_message,
            approx_tokens=approx_tokens,
            effective_task_id=effective_task_id,
            api_call_count=api_call_count,
            compression_attempts=compression_attempts,
            max_compression_attempts=max_compression_attempts,
            time_module=time_module,
        )

    return _proceed(
        messages=messages,
        active_system_prompt=active_system_prompt,
        conversation_history=conversation_history,
        compression_attempts=compression_attempts,
        is_context_length_error=False,
    )


def _handle_long_context_tier(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    active_system_prompt: str | None,
    conversation_history: List[Dict[str, Any]] | None,
    system_message: str | None,
    approx_tokens: int,
    effective_task_id: str,
    api_call_count: int,
    compression_attempts: int,
    max_compression_attempts: int,
    time_module: Any,
) -> ContextRecoveryResult:
    reduced_ctx = 200000
    compressor = agent.context_compressor
    old_ctx = compressor.context_length
    if old_ctx > reduced_ctx:
        _update_context_length(agent, compressor, reduced_ctx, persistable=False)
        agent._vprint(
            f"{agent.log_prefix}⚠️  Anthropic long-context tier requires extra usage — "
            f"reducing context: {old_ctx:,} → {reduced_ctx:,} tokens",
            force=True,
        )
    compression_attempts += 1
    if compression_attempts <= max_compression_attempts:
        original_len = len(messages)
        messages, active_system_prompt = agent._compress_context(
            messages,
            system_message,
            approx_tokens=approx_tokens,
            task_id=effective_task_id,
        )
        conversation_history = None
        if len(messages) < original_len or old_ctx > reduced_ctx:
            agent._emit_status(f"🗜️ Context reduced to {reduced_ctx:,} tokens (was {old_ctx:,}), retrying...")
            time_module.sleep(2)
            return _break_retry(messages, active_system_prompt, conversation_history, compression_attempts, False)
    return _proceed(messages, active_system_prompt, conversation_history, compression_attempts, False)


def _handle_payload_too_large(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    active_system_prompt: str | None,
    conversation_history: List[Dict[str, Any]] | None,
    system_message: str | None,
    approx_tokens: int,
    effective_task_id: str,
    api_call_count: int,
    compression_attempts: int,
    max_compression_attempts: int,
    time_module: Any,
) -> ContextRecoveryResult:
    compression_attempts += 1
    if compression_attempts > max_compression_attempts:
        return _compression_exhausted(
            agent=agent,
            messages=messages,
            conversation_history=conversation_history,
            api_call_count=api_call_count,
            error=f"Request payload too large: max compression attempts ({max_compression_attempts}) reached.",
            log_error=f"{agent.log_prefix}413 compression failed after {max_compression_attempts} attempts.",
            message=f"{agent.log_prefix}❌ Max compression attempts ({max_compression_attempts}) reached for payload-too-large error.",
            compression_attempts=compression_attempts,
            active_system_prompt=active_system_prompt,
            is_context_length_error=False,
        )
    agent._emit_status(
        f"⚠️  Request payload too large (413) — compression attempt "
        f"{compression_attempts}/{max_compression_attempts}..."
    )
    original_len = len(messages)
    messages, active_system_prompt = agent._compress_context(
        messages,
        system_message,
        approx_tokens=approx_tokens,
        task_id=effective_task_id,
    )
    conversation_history = None
    if len(messages) < original_len:
        agent._emit_status(f"🗜️ Compressed {original_len} → {len(messages)} messages, retrying...")
        time_module.sleep(2)
        return _break_retry(messages, active_system_prompt, conversation_history, compression_attempts, False)

    agent._vprint(f"{agent.log_prefix}❌ Payload too large and cannot compress further.", force=True)
    agent._vprint(f"{agent.log_prefix}   💡 Try /new to start a fresh conversation, or /compress to retry compression.", force=True)
    logger.error("%s413 payload too large. Cannot compress further.", agent.log_prefix)
    agent._persist_session(messages, conversation_history)
    return _return(
        messages,
        active_system_prompt,
        conversation_history,
        compression_attempts,
        False,
        {
            "messages": messages,
            "completed": False,
            "api_calls": api_call_count,
            "error": "Request payload too large (413). Cannot compress further.",
            "partial": True,
            "failed": True,
            "compression_exhausted": True,
        },
    )


def _handle_context_overflow(
    *,
    agent: Any,
    error_msg: str,
    messages: List[Dict[str, Any]],
    active_system_prompt: str | None,
    conversation_history: List[Dict[str, Any]] | None,
    system_message: str | None,
    approx_tokens: int,
    effective_task_id: str,
    api_call_count: int,
    compression_attempts: int,
    max_compression_attempts: int,
    time_module: Any,
) -> ContextRecoveryResult:
    compressor = agent.context_compressor
    old_ctx = compressor.context_length
    available_out = parse_available_output_tokens_from_error(error_msg)
    if available_out is not None:
        return _handle_output_cap_overflow(
            agent, messages, active_system_prompt, conversation_history,
            api_call_count, compression_attempts, max_compression_attempts,
            old_ctx, available_out,
        )

    parsed_limit = parse_context_limit_from_error(error_msg)
    new_ctx = _next_context_limit(agent, error_msg, old_ctx, parsed_limit)
    if new_ctx and new_ctx < old_ctx:
        _update_context_length(agent, compressor, new_ctx, persistable=bool(parsed_limit and parsed_limit == new_ctx))
        agent._vprint(f"{agent.log_prefix}⚠️  Context length exceeded — stepping down: {old_ctx:,} → {new_ctx:,} tokens", force=True)
    else:
        agent._vprint(f"{agent.log_prefix}⚠️  Context length exceeded at minimum tier — attempting compression...", force=True)

    compression_attempts += 1
    if compression_attempts > max_compression_attempts:
        return _compression_exhausted(
            agent=agent,
            messages=messages,
            conversation_history=conversation_history,
            api_call_count=api_call_count,
            error=f"Context length exceeded: max compression attempts ({max_compression_attempts}) reached.",
            log_error=f"{agent.log_prefix}Context compression failed after {max_compression_attempts} attempts.",
            message=f"{agent.log_prefix}❌ Max compression attempts ({max_compression_attempts}) reached.",
            compression_attempts=compression_attempts,
            active_system_prompt=active_system_prompt,
            is_context_length_error=True,
        )
    agent._emit_status(f"🗜️ Context too large (~{approx_tokens:,} tokens) — compressing ({compression_attempts}/{max_compression_attempts})...")
    original_len = len(messages)
    messages, active_system_prompt = agent._compress_context(
        messages,
        system_message,
        approx_tokens=approx_tokens,
        task_id=effective_task_id,
    )
    conversation_history = None
    if len(messages) < original_len or (new_ctx and new_ctx < old_ctx):
        if len(messages) < original_len:
            agent._emit_status(f"🗜️ Compressed {original_len} → {len(messages)} messages, retrying...")
        time_module.sleep(2)
        return _break_retry(messages, active_system_prompt, conversation_history, compression_attempts, True)

    agent._vprint(f"{agent.log_prefix}❌ Context length exceeded and cannot compress further.", force=True)
    agent._vprint(
        f"{agent.log_prefix}   💡 The conversation has accumulated too much content. "
        "Try /new to start fresh, or /compress to manually trigger compression.",
        force=True,
    )
    logger.error("%sContext length exceeded: %s tokens. Cannot compress further.", agent.log_prefix, f"{approx_tokens:,}")
    agent._persist_session(messages, conversation_history)
    return _return(
        messages,
        active_system_prompt,
        conversation_history,
        compression_attempts,
        True,
        {
            "messages": messages,
            "completed": False,
            "api_calls": api_call_count,
            "error": f"Context length exceeded ({approx_tokens:,} tokens). Cannot compress further.",
            "partial": True,
            "failed": True,
            "compression_exhausted": True,
        },
    )


def _handle_output_cap_overflow(
    agent: Any,
    messages: List[Dict[str, Any]],
    active_system_prompt: str | None,
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
    compression_attempts: int,
    max_compression_attempts: int,
    old_ctx: int,
    available_out: int,
) -> ContextRecoveryResult:
    safe_out = max(1, available_out - 64)
    agent._ephemeral_max_output_tokens = safe_out
    agent._vprint(
        f"{agent.log_prefix}⚠️  Output cap too large for current prompt — "
        f"retrying with max_tokens={safe_out:,} "
        f"(available_tokens={available_out:,}; context_length unchanged at {old_ctx:,})",
        force=True,
    )
    compression_attempts += 1
    if compression_attempts > max_compression_attempts:
        return _compression_exhausted(
            agent=agent,
            messages=messages,
            conversation_history=conversation_history,
            api_call_count=api_call_count,
            error=f"Context length exceeded: max compression attempts ({max_compression_attempts}) reached.",
            log_error=f"{agent.log_prefix}Context compression failed after {max_compression_attempts} attempts.",
            message=f"{agent.log_prefix}❌ Max compression attempts ({max_compression_attempts}) reached.",
            compression_attempts=compression_attempts,
            active_system_prompt=active_system_prompt,
            is_context_length_error=True,
        )
    return _break_retry(messages, active_system_prompt, conversation_history, compression_attempts, True)


def _next_context_limit(agent: Any, error_msg: str, old_ctx: int, parsed_limit: int | None) -> int | None:
    provider = (getattr(agent, "provider", "") or "").lower()
    base = (getattr(agent, "base_url", "") or "").rstrip("/").lower()
    is_minimax = provider in {"minimax", "minimax-cn"} or base.startswith(
        ("https://api.minimax.io/anthropic", "https://api.minimaxi.com/anthropic")
    )
    minimax_delta_only = is_minimax and parsed_limit is None and "context window exceeds limit (" in error_msg
    if parsed_limit and parsed_limit < old_ctx:
        agent._vprint(f"{agent.log_prefix}Context limit detected from API: {parsed_limit:,} tokens (was {old_ctx:,})", force=True)
        return parsed_limit
    if minimax_delta_only:
        agent._vprint(
            f"{agent.log_prefix}Provider reported overflow amount only; keeping context_length at {old_ctx:,} tokens and compressing.",
            force=True,
        )
        return old_ctx
    return get_next_probe_tier(old_ctx)


def _update_context_length(agent: Any, compressor: Any, context_length: int, *, persistable: bool) -> None:
    compressor.update_model(
        model=agent.model,
        context_length=context_length,
        base_url=agent.base_url,
        api_key=getattr(agent, "api_key", ""),
        provider=agent.provider,
        api_mode=agent.api_mode,
    )
    if hasattr(compressor, "_context_probed"):
        compressor._context_probed = True
        compressor._context_probe_persistable = persistable


def _print_github_413_hint(agent: Any, status_code: int | None) -> None:
    if not (
        status_code == 413
        and isinstance(agent.base_url, str)
        and "models.inference.ai.azure.com" in agent.base_url
    ):
        return
    agent._vprint(f"{agent.log_prefix}   💡 GitHub Models free tier (models.inference.ai.azure.com) caps every", force=True)
    agent._vprint(f"{agent.log_prefix}      request at ~8K tokens. Miho' system prompt + tool schemas baseline", force=True)
    agent._vprint(f"{agent.log_prefix}      exceeds that floor, so this endpoint cannot run an agentic loop.", force=True)
    agent._vprint(f"{agent.log_prefix}      Use the `copilot` provider with a Copilot subscription token (`miho", force=True)
    agent._vprint(f"{agent.log_prefix}      setup` → GitHub Copilot), or pick any other provider.", force=True)


def _compression_exhausted(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
    error: str,
    log_error: str,
    message: str,
    compression_attempts: int,
    active_system_prompt: str | None,
    is_context_length_error: bool,
) -> ContextRecoveryResult:
    agent._vprint(message, force=True)
    agent._vprint(f"{agent.log_prefix}   💡 Try /new to start a fresh conversation, or /compress to retry compression.", force=True)
    logger.error(log_error)
    agent._persist_session(messages, conversation_history)
    return _return(
        messages,
        active_system_prompt,
        conversation_history,
        compression_attempts,
        is_context_length_error,
        {
            "messages": messages,
            "completed": False,
            "api_calls": api_call_count,
            "error": error,
            "partial": True,
            "failed": True,
            "compression_exhausted": True,
        },
    )


def _break_retry(
    messages: List[Dict[str, Any]],
    active_system_prompt: str | None,
    conversation_history: List[Dict[str, Any]] | None,
    compression_attempts: int,
    is_context_length_error: bool,
) -> ContextRecoveryResult:
    return ContextRecoveryResult(
        "break_retry",
        messages,
        active_system_prompt,
        conversation_history,
        compression_attempts,
        is_context_length_error,
        True,
    )


def _return(
    messages: List[Dict[str, Any]],
    active_system_prompt: str | None,
    conversation_history: List[Dict[str, Any]] | None,
    compression_attempts: int,
    is_context_length_error: bool,
    return_value: Dict[str, Any],
) -> ContextRecoveryResult:
    return ContextRecoveryResult(
        "return",
        messages,
        active_system_prompt,
        conversation_history,
        compression_attempts,
        is_context_length_error,
        False,
        return_value,
    )


def _proceed(
    messages: List[Dict[str, Any]],
    active_system_prompt: str | None,
    conversation_history: List[Dict[str, Any]] | None,
    compression_attempts: int,
    is_context_length_error: bool,
) -> ContextRecoveryResult:
    return ContextRecoveryResult(
        "proceed",
        messages,
        active_system_prompt,
        conversation_history,
        compression_attempts,
        is_context_length_error,
        False,
    )
