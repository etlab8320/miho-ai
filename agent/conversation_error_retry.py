"""Generic API-error retry decisions for the conversation loop."""

from __future__ import annotations

import json
import logging
import ssl
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from agent.conversation_context_recovery import handle_context_recovery
from agent.conversation_error_backoff import handle_max_retries, wait_before_retry
from agent.error_classifier import FailoverReason
from agent.nous_rate_guard import is_genuine_nous_rate_limit, record_nous_rate_limit
from utils import base_url_host_matches

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorRetryResult:
    action: str
    retry_count: int
    compression_attempts: int
    primary_recovery_attempted: bool
    messages: List[Dict[str, Any]]
    conversation_history: List[Dict[str, Any]] | None
    active_system_prompt: str | None
    restart_with_compressed_messages: bool
    return_value: Dict[str, Any] | None = None


def handle_api_error_retry(
    *,
    agent: Any,
    api_error: Exception,
    classified: Any,
    status_code: int | None,
    error_context: Dict[str, Any],
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    active_system_prompt: str | None,
    system_message: str | None,
    approx_tokens: int,
    effective_task_id: str,
    api_call_count: int,
    api_messages: List[Dict[str, Any]],
    api_kwargs: Dict[str, Any] | None,
    retry_count: int,
    max_retries: int,
    compression_attempts: int,
    max_compression_attempts: int,
    primary_recovery_attempted: bool,
    recovered_with_pool: bool,
    api_start_time: float,
    backoff_fn: Callable[..., float],
    time_module: Any,
    pool_may_recover_fn: Callable[..., bool],
) -> ErrorRetryResult:
    """Run generic retry/failover handling after one-shot recoveries."""

    retry_count += 1
    elapsed_time = time_module.time() - api_start_time
    agent._touch_activity(f"API error recovery (attempt {retry_count}/{max_retries})")
    error_type = type(api_error).__name__
    error_msg = str(api_error).lower()
    error_summary = _log_api_error(
        agent=agent,
        api_error=api_error,
        retry_count=retry_count,
        max_retries=max_retries,
        error_type=error_type,
        status_code=status_code,
        elapsed_time=elapsed_time,
        api_messages=api_messages,
        approx_tokens=approx_tokens,
    )
    provider = getattr(agent, "provider", "unknown")
    base = getattr(agent, "base_url", "unknown")
    model = getattr(agent, "model", "unknown")
    _print_openrouter_tool_hint(agent, error_msg, model)

    interrupt = _interrupted_during_error_handling(
        agent, api_error, error_type, messages, conversation_history, api_call_count
    )
    if interrupt is not None:
        return _return(retry_count, compression_attempts, primary_recovery_attempted, messages, conversation_history, active_system_prompt, interrupt)

    context_result = handle_context_recovery(
        agent=agent,
        classified=classified,
        status_code=status_code,
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
    messages = context_result.messages
    active_system_prompt = context_result.active_system_prompt
    conversation_history = context_result.conversation_history
    compression_attempts = context_result.compression_attempts
    if context_result.action == "return":
        return _return(retry_count, compression_attempts, primary_recovery_attempted, messages, conversation_history, active_system_prompt, context_result.return_value)
    if context_result.action == "break_retry":
        return ErrorRetryResult("break_retry", retry_count, compression_attempts, primary_recovery_attempted, messages, conversation_history, active_system_prompt, True)

    is_rate_limited = classified.reason in {FailoverReason.rate_limit, FailoverReason.billing}
    if _try_eager_rate_limit_fallback(
        agent, classified, is_rate_limited, pool_may_recover_fn
    ):
        return ErrorRetryResult("continue", 0, 0, False, messages, conversation_history, active_system_prompt, False)
    if _record_nous_rate_limit_if_needed(
        agent=agent,
        api_error=api_error,
        classified=classified,
        is_rate_limited=is_rate_limited,
        recovered_with_pool=recovered_with_pool,
        error_context=error_context,
    ):
        return ErrorRetryResult("continue", max_retries, compression_attempts, primary_recovery_attempted, messages, conversation_history, active_system_prompt, False)

    client_error = _is_non_retryable_client_error(
        agent=agent,
        api_error=api_error,
        classified=classified,
        is_context_length_error=context_result.is_context_length_error,
    )
    if client_error:
        result = _handle_client_error(
            agent=agent,
            api_error=api_error,
            classified=classified,
            status_code=status_code,
            provider=provider,
            base=base,
            model=model,
            messages=messages,
            conversation_history=conversation_history,
            api_call_count=api_call_count,
            api_messages=api_messages,
            api_kwargs=api_kwargs,
            approx_tokens=approx_tokens,
        )
        if result.action == "continue":
            return ErrorRetryResult("continue", 0, 0, False, messages, conversation_history, active_system_prompt, False)
        return _return(retry_count, compression_attempts, primary_recovery_attempted, messages, conversation_history, active_system_prompt, result.return_value)

    if retry_count >= max_retries:
        max_result = handle_max_retries(
            agent=agent,
            api_error=api_error,
            error_msg=error_msg,
            error_summary=error_summary,
            is_rate_limited=is_rate_limited,
            provider=provider,
            model=model,
            messages=messages,
            conversation_history=conversation_history,
            api_call_count=api_call_count,
            api_messages=api_messages,
            api_kwargs=api_kwargs,
            approx_tokens=approx_tokens,
            retry_count=retry_count,
            max_retries=max_retries,
            primary_recovery_attempted=primary_recovery_attempted,
        )
        if max_result.action == "continue":
            return ErrorRetryResult("continue", 0, compression_attempts, True, messages, conversation_history, active_system_prompt, False)
        if max_result.action == "fallback":
            return ErrorRetryResult("continue", 0, 0, False, messages, conversation_history, active_system_prompt, False)
        return _return(retry_count, compression_attempts, primary_recovery_attempted, messages, conversation_history, active_system_prompt, max_result.return_value)

    wait_result = wait_before_retry(
        agent=agent,
        api_error=api_error,
        is_rate_limited=is_rate_limited,
        retry_count=retry_count,
        max_retries=max_retries,
        messages=messages,
        conversation_history=conversation_history,
        api_call_count=api_call_count,
        backoff_fn=backoff_fn,
        time_module=time_module,
    )
    if wait_result is not None:
        return _return(retry_count, compression_attempts, primary_recovery_attempted, messages, conversation_history, active_system_prompt, wait_result)
    return ErrorRetryResult("proceed", retry_count, compression_attempts, primary_recovery_attempted, messages, conversation_history, active_system_prompt, False)


def _log_api_error(
    *,
    agent: Any,
    api_error: Exception,
    retry_count: int,
    max_retries: int,
    error_type: str,
    status_code: int | None,
    elapsed_time: float,
    api_messages: List[Dict[str, Any]],
    approx_tokens: int,
) -> str:
    summary = agent._summarize_api_error(api_error)
    logger.warning(
        "API call failed (attempt %s/%s) error_type=%s %s summary=%s",
        retry_count,
        max_retries,
        error_type,
        agent._client_log_context(),
        summary,
    )
    status = f" [HTTP {status_code}]" if status_code else ""
    agent._vprint(f"{agent.log_prefix}⚠️  API call failed (attempt {retry_count}/{max_retries}): {error_type}{status}", force=True)
    agent._vprint(f"{agent.log_prefix}   🔌 Provider: {getattr(agent, 'provider', 'unknown')}  Model: {getattr(agent, 'model', 'unknown')}", force=True)
    agent._vprint(f"{agent.log_prefix}   🌐 Endpoint: {getattr(agent, 'base_url', 'unknown')}", force=True)
    agent._vprint(f"{agent.log_prefix}   📝 Error: {summary}", force=True)
    if status_code and status_code < 500:
        body = getattr(api_error, "body", None)
        body_text = str(body)[:300] if body else None
        if body_text:
            agent._vprint(f"{agent.log_prefix}   📋 Details: {body_text}", force=True)
    agent._vprint(f"{agent.log_prefix}   ⏱️  Elapsed: {elapsed_time:.2f}s  Context: {len(api_messages)} msgs, ~{approx_tokens:,} tokens")
    return summary


def _print_openrouter_tool_hint(agent: Any, error_msg: str, model: str) -> None:
    if not (agent._is_openrouter_url() and "support tool use" in error_msg):
        return
    agent._vprint(f"{agent.log_prefix}   💡 No OpenRouter providers for {model} support tool calling with your current settings.", force=True)
    if agent.providers_allowed:
        agent._vprint(f"{agent.log_prefix}      Your provider_routing.only restriction is filtering out tool-capable providers.", force=True)
        agent._vprint(f"{agent.log_prefix}      Try removing the restriction or adding providers that support tools for this model.", force=True)
    agent._vprint(f"{agent.log_prefix}      Check which providers support tools: https://openrouter.ai/models/{model}", force=True)


def _interrupted_during_error_handling(
    agent: Any,
    api_error: Exception,
    error_type: str,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
) -> Dict[str, Any] | None:
    if not agent._interrupt_requested:
        return None
    agent._vprint(f"{agent.log_prefix}⚡ Interrupt detected during error handling, aborting retries.", force=True)
    agent._persist_session(messages, conversation_history)
    agent.clear_interrupt()
    return {
        "final_response": f"Operation interrupted: handling API error ({error_type}: {agent._clean_error_message(str(api_error))}).",
        "messages": messages,
        "api_calls": api_call_count,
        "completed": False,
        "interrupted": True,
    }


def _try_eager_rate_limit_fallback(agent: Any, classified: Any, is_rate_limited: bool, pool_may_recover_fn: Callable[..., bool]) -> bool:
    if not (is_rate_limited and agent._fallback_index < len(agent._fallback_chain)):
        return False
    pool_may_recover = pool_may_recover_fn(
        agent._credential_pool,
        provider=agent.provider,
        base_url=getattr(agent, "base_url", None),
    )
    if pool_may_recover:
        return False
    agent._emit_status("⚠️ Rate limited — switching to fallback provider...")
    return bool(agent._try_activate_fallback(reason=classified.reason))


def _record_nous_rate_limit_if_needed(
    *,
    agent: Any,
    api_error: Exception,
    classified: Any,
    is_rate_limited: bool,
    recovered_with_pool: bool,
    error_context: Dict[str, Any],
) -> bool:
    if not (
        is_rate_limited
        and agent.provider == "nous"
        and classified.reason == FailoverReason.rate_limit
        and not recovered_with_pool
    ):
        return False
    try:
        response = getattr(api_error, "response", None)
        headers = getattr(response, "headers", None) if response else None
        genuine = is_genuine_nous_rate_limit(headers=headers, last_known_state=agent._rate_limit_state)
        if genuine:
            record_nous_rate_limit(headers=headers, error_context=error_context)
            return True
        logger.info("Nous 429 looks like upstream capacity -- not tripping cross-session breaker.")
    except Exception:
        pass
    return False


def _is_non_retryable_client_error(
    *,
    agent: Any,
    api_error: Exception,
    classified: Any,
    is_context_length_error: bool,
) -> bool:
    is_local_validation_error = (
        isinstance(api_error, (ValueError, TypeError))
        and not isinstance(api_error, (UnicodeEncodeError, json.JSONDecodeError))
        and not (
            isinstance(api_error, TypeError)
            and "NoneType" in str(api_error)
            and "not iterable" in str(api_error)
            and (
                getattr(agent, "api_mode", "") == "codex_responses"
                or str(getattr(agent, "provider", "")).lower() == "openai-codex"
            )
        )
        and not isinstance(api_error, ssl.SSLError)
    )
    classified_client = (
        not classified.retryable
        and not classified.should_compress
        and classified.reason
        not in {
            FailoverReason.rate_limit,
            FailoverReason.billing,
            FailoverReason.overloaded,
            FailoverReason.context_overflow,
            FailoverReason.payload_too_large,
            FailoverReason.long_context_tier,
            FailoverReason.thinking_signature,
        }
    )
    return (is_local_validation_error or classified_client) and not is_context_length_error


@dataclass(frozen=True)
class _ClientErrorResult:
    action: str
    return_value: Dict[str, Any] | None = None


def _handle_client_error(
    *,
    agent: Any,
    api_error: Exception,
    classified: Any,
    status_code: int | None,
    provider: str,
    base: str,
    model: str,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
    api_messages: List[Dict[str, Any]],
    api_kwargs: Dict[str, Any] | None,
    approx_tokens: int,
) -> _ClientErrorResult:
    agent._emit_status(f"⚠️ Non-retryable error (HTTP {status_code}) — trying fallback...")
    if agent._try_activate_fallback():
        return _ClientErrorResult("continue")
    if api_kwargs is not None:
        agent._dump_api_request_debug(api_kwargs, reason="non_retryable_client_error", error=api_error)
    agent._emit_status(f"❌ Non-retryable error (HTTP {status_code}): {agent._summarize_api_error(api_error)}")
    agent._vprint(f"{agent.log_prefix}❌ Non-retryable client error (HTTP {status_code}). Aborting.", force=True)
    agent._vprint(f"{agent.log_prefix}   🔌 Provider: {provider}  Model: {model}", force=True)
    agent._vprint(f"{agent.log_prefix}   🌐 Endpoint: {base}", force=True)
    _print_client_error_guidance(agent, classified, status_code, provider, model, base)
    logger.error("%sNon-retryable client error: %s", agent.log_prefix, api_error)
    if status_code == 400 and (approx_tokens > 50000 or len(api_messages) > 80):
        agent._vprint(f"{agent.log_prefix}⚠️  Skipping session persistence for large failed session to prevent growth loop.", force=True)
    else:
        agent._persist_session(messages, conversation_history)
    return _ClientErrorResult(
        "return",
        {
            "final_response": None,
            "messages": messages,
            "api_calls": api_call_count,
            "completed": False,
            "failed": True,
            "error": str(api_error),
        },
    )


def _print_client_error_guidance(agent: Any, classified: Any, status_code: int | None, provider: str, model: str, base: str) -> None:
    if classified.is_auth or classified.reason == FailoverReason.billing:
        if provider in {"openai-codex", "xai-oauth"} and status_code == 401:
            if provider == "openai-codex":
                agent._vprint(f"{agent.log_prefix}   💡 Codex OAuth token was rejected (HTTP 401). Your token may have been", force=True)
                agent._vprint(f"{agent.log_prefix}      refreshed by another client (Codex CLI, VS Code). To fix:", force=True)
                agent._vprint(f"{agent.log_prefix}      1. Run `codex` in your terminal to generate fresh tokens.", force=True)
                agent._vprint(f"{agent.log_prefix}      2. Then run `miho auth` to re-authenticate.", force=True)
            else:
                agent._vprint(f"{agent.log_prefix}   💡 xAI OAuth token was rejected (HTTP 401). To fix:", force=True)
                agent._vprint(f"{agent.log_prefix}      re-authenticate with xAI Grok OAuth (SuperGrok Subscription) from `miho model`.", force=True)
        else:
            agent._vprint(f"{agent.log_prefix}   💡 Your API key was rejected by the provider. Check:", force=True)
            agent._vprint(f"{agent.log_prefix}      • Is the key valid? Run: miho setup", force=True)
            agent._vprint(f"{agent.log_prefix}      • Does your account have access to {model}?", force=True)
            if base_url_host_matches(str(base), "openrouter.ai"):
                agent._vprint(f"{agent.log_prefix}      • Check credits: https://openrouter.ai/settings/credits", force=True)
    else:
        agent._vprint(f"{agent.log_prefix}   💡 This type of error won't be fixed by retrying.", force=True)


def _return(
    retry_count: int,
    compression_attempts: int,
    primary_recovery_attempted: bool,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    active_system_prompt: str | None,
    return_value: Dict[str, Any] | None,
) -> ErrorRetryResult:
    return ErrorRetryResult(
        "return",
        retry_count,
        compression_attempts,
        primary_recovery_attempted,
        messages,
        conversation_history,
        active_system_prompt,
        False,
        return_value,
    )
